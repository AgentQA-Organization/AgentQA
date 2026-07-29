import os
import stat
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
PHASE2 = SKILL / "scripts" / "phase2-wrapper.sh"
PRECHECKS = SKILL / "scripts" / "green-prechecks.py"


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def env_with_bin(project, fake_bin, **extra):
    env = os.environ.copy()
    env.update(extra)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    return env


def write_config(project, text):
    config = project / ".agentqa" / "config.yml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")


def test_explore_respects_never_and_android_flag(tmp_path):
    fake_bin = tmp_path / "bin"
    calls = tmp_path / "calls"
    executable(fake_bin / "agent-device", f"#!/usr/bin/env bash\necho \"$*\" >> {calls!s}\n")
    write_config(tmp_path, "platform: android\nreset_app_data: never\n")
    result = subprocess.run(
        ["bash", str(PHASE2), "explore", "--app-id", "com.example.app"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert calls.read_text().strip() == "open com.example.app --platform android"
    assert "skipped" in result.stdout


def test_explore_always_calls_reset_before_open(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_init = tmp_path / "agentqa-init"
    calls = tmp_path / "calls"
    executable(fake_init / "scripts" / "reset-app-data.sh", f"#!/usr/bin/env bash\necho \"reset $*\" >> {calls!s}\n")
    executable(fake_bin / "agent-device", f"#!/usr/bin/env bash\necho \"device $*\" >> {calls!s}\n")
    write_config(tmp_path, "platform: ios\nreset_app_data: always\n")
    result = subprocess.run(
        ["bash", str(PHASE2), "explore", "--app-id", "com.example.app"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin, AGENTQA_INIT_BASE=str(fake_init)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == ["reset com.example.app", "device open com.example.app"]


def test_explore_fails_when_reset_sibling_is_missing(tmp_path):
    fake_bin = tmp_path / "bin"
    executable(fake_bin / "agent-device", "#!/usr/bin/env bash\nexit 0\n")
    write_config(tmp_path, "platform: ios\nreset_app_data: always\n")
    result = subprocess.run(
        ["bash", str(PHASE2), "explore", "--app-id", "com.example.app"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin, AGENTQA_INIT_BASE=str(tmp_path / "missing")),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "reset script not found" in result.stderr


def test_wrapper_rejects_unknown_or_incomplete_options(tmp_path):
    result = subprocess.run(
        ["bash", str(PHASE2), "note-propose", "--wat"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unknown" in result.stderr


def test_ios_prechecks_use_nested_appium_port(tmp_path):
    fake_bin = tmp_path / "bin"
    calls = tmp_path / "calls"
    executable(
        fake_bin / "xcrun",
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == *listapps* ]]; then echo com.example.app; else echo Booted; fi\n",
    )
    executable(fake_bin / "nc", f"#!/usr/bin/env bash\necho \"$*\" >> {calls!s}\nexit 0\n")
    write_config(
        tmp_path,
        "platform: ios\nbundle_id: com.example.app\nappium:\n  port: 5555\n",
    )
    result = subprocess.run(
        [sys.executable, str(PRECHECKS), "check"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert calls.read_text().strip() == "-z 127.0.0.1 5555"


def test_android_prechecks_do_not_treat_devices_header_as_a_device(tmp_path):
    fake_bin = tmp_path / "bin"
    executable(fake_bin / "adb", "#!/usr/bin/env bash\necho unknown\nexit 1\n")
    executable(fake_bin / "nc", "#!/usr/bin/env bash\nexit 0\n")
    write_config(tmp_path, "platform: android\napp_package: com.example.app\n")
    result = subprocess.run(
        [sys.executable, str(PRECHECKS), "check"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "no Android device" in result.stderr


def test_prechecks_fail_when_appium_is_unavailable(tmp_path):
    fake_bin = tmp_path / "bin"
    executable(fake_bin / "xcrun", "#!/usr/bin/env bash\necho Booted\necho com.example.app\n")
    executable(fake_bin / "nc", "#!/usr/bin/env bash\nexit 1\n")
    write_config(tmp_path, "platform: ios\nbundle_id: com.example.app\n")
    result = subprocess.run(
        [sys.executable, str(PRECHECKS), "check"],
        cwd=tmp_path,
        env=env_with_bin(tmp_path, fake_bin),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Appium not running" in result.stderr
