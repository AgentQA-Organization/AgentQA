#!/usr/bin/env python3
"""Check device, installed app, and Appium before the green loop."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


CONFIG = Path(".agentqa/config.yml")


def _scalar(key: str) -> Optional[str]:
    if not CONFIG.is_file():
        return None
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}:"):
            value = line.split(":", 1)[1].split("#", 1)[0].strip()
            return value.strip('"').strip("'")
    return None


def _appium_port() -> str:
    if not CONFIG.is_file():
        return "4723"
    content = CONFIG.read_text(encoding="utf-8")
    nested = re.search(r"^appium:\s*(?:#.*)?\n(?:^[ \t]+.*\n)*?^[ \t]+port:\s*(\d+)", content, re.M)
    if nested:
        return nested.group(1)
    return _scalar("appium_port") or "4723"


def _run(command: List[str], timeout: int = 10) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def check() -> List[str]:
    errors: List[str] = []
    platform = (_scalar("platform") or "").lower()
    if platform not in {"ios", "android"}:
        return [f"config platform must be ios or android (got: {platform!r})"]

    if platform == "android":
        state = _run(["adb", "get-state"])
        if not state or state.returncode or state.stdout.strip() != "device":
            errors.append("no Android device/emulator")
        else:
            package = _scalar("app_package")
            if not package:
                errors.append("app_package missing from config")
            else:
                packages = _run(["adb", "shell", "pm", "list", "packages"], timeout=15)
                if not packages:
                    errors.append("adb shell not available")
                elif f"package:{package}" not in packages.stdout.splitlines():
                    errors.append(f"app {package!r} not installed")
    else:
        devices = _run(["xcrun", "simctl", "list", "devices", "booted"])
        if not devices:
            errors.append("xcrun/simctl not available")
        elif devices.returncode or "Booted" not in devices.stdout:
            errors.append("no booted iOS simulator")
        else:
            bundle_id = _scalar("bundle_id")
            if not bundle_id:
                errors.append("bundle_id missing from config")
            else:
                apps = _run(["xcrun", "simctl", "listapps", "booted"])
                if not apps:
                    errors.append("xcrun simctl listapps not available")
                elif apps.returncode or bundle_id not in apps.stdout:
                    errors.append(f"app {bundle_id!r} not installed")

    port = _appium_port()
    appium = _run(["nc", "-z", "127.0.0.1", port], timeout=5)
    if not appium or appium.returncode:
        errors.append(f"Appium not running on 127.0.0.1:{port}")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["check"]):
        print("Usage: green-prechecks.py [check]", file=sys.stderr)
        return 2
    errors = check()
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("All green-loop preconditions met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
