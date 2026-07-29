#!/usr/bin/env python3
"""Mechanical state engine for agentqa-write-test.

The checkpoint keeps a JSON body while retaining the historical `.md` filename.
Only this script may mutate the checkpoint.  Phase instructions record evidence;
the controller validates and transitions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, NoReturn, Optional


DEFAULT_PATH = Path(".agentqa/memory/.run-checkpoint.md")
SESSION_REQUIREMENT = Path(".agentqa/memory/.session-requirement.md")
MAX_PHASE = 5
STATUSES = {"IN_PROGRESS", "WAITING_FOR_USER", "COMPLETE"}
PHASE_CHECKS = {
    1: {"codegraph_indexed", "source_read", "clarification_done"},
    2: {"exploration_done"},
    3: {"identifiers_verified"},
    4: {"test_approved"},
    5: {"capture_done"},
}


def fail(message: str) -> NoReturn:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _eval_log(argv: List[str]) -> None:
    """Emit structured protocol evidence only inside the deterministic eval."""
    state_dir = os.environ.get("AGENTQA_EVAL_STATE")
    if not state_dir:
        return
    target = Path(state_dir) / "calls.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "tool": "checkpoint.py", "argv": argv}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"checkpoint not found at {path}")
    except json.JSONDecodeError as exc:
        fail(f"checkpoint is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("checkpoint root must be a JSON object")
    return data


def _next_action(data: dict) -> str:
    status = data.get("phase_status")
    phase = data.get("current_phase")
    if status == "WAITING_FOR_USER":
        return "wait-for-user"
    if status == "COMPLETE":
        if data.get("validated_phase") == phase:
            return "controller-finalize" if phase == MAX_PHASE else "controller-advance"
        return "controller-validate"
    return f"execute-phase-{phase}"


def _write(path: Path, data: dict) -> None:
    data["next_action"] = _next_action(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _clear_token(data: dict) -> None:
    data.pop("validated_phase", None)


def _require_status(data: dict, status: str, operation: str) -> None:
    actual = data.get("phase_status")
    if actual != status:
        fail(f"{operation} requires {status}, got {actual}")


def _config_value(key: str, section: Optional[str] = None) -> Optional[str]:
    """Read the simple scalar shapes used by `.agentqa/config.yml`."""
    config = Path(".agentqa/config.yml")
    if not config.is_file():
        return None
    in_section = section is None
    for raw in config.read_text(encoding="utf-8").splitlines():
        content = raw.split("#", 1)[0].rstrip()
        if not content.strip():
            continue
        if section is not None and raw[:1] and not raw[:1].isspace():
            in_section = content.strip() == f"{section}:"
            continue
        if in_section and content.strip().startswith(f"{key}:"):
            return content.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _checks(data: dict) -> Dict[str, dict]:
    return {item.get("name", ""): item for item in data.get("completed_checks", [])}


def _upsert_check(data: dict, name: str, evidence: str) -> None:
    checks = data.setdefault("completed_checks", [])
    entry = {"name": name, "evidence": evidence, "ok": True}
    for index, existing in enumerate(checks):
        if existing.get("name") == name:
            checks[index] = entry
            return
    checks.append(entry)


def _artifact(data: dict, name: str) -> str:
    return str(data.get("artifacts", {}).get(name, ""))


def cmd_init(args: argparse.Namespace) -> None:
    path = args.path
    if path.exists():
        fail(f"checkpoint already exists at {path}; use status to resume it")

    platform = args.platform or _config_value("platform") or "ios"
    build_policy = args.build_policy or _config_value("policy", "build") or "human"
    reset_policy = args.reset_policy or _config_value("reset_app_data") or "always"
    if platform not in {"ios", "android"}:
        fail(f"invalid platform: {platform}")
    if build_policy not in {"human", "agent"}:
        fail(f"invalid build policy: {build_policy}")
    if reset_policy not in {"always", "never"}:
        fail(f"invalid reset_app_data policy: {reset_policy}")

    mode = args.mode
    test_file = str(args.test_file or "")
    flow_name = args.flow
    if mode == "diagnose":
        if not args.test_file or not args.test_file.is_file():
            fail("diagnose mode requires an existing --test-file")
        stem = args.test_file.stem
        flow_name = flow_name or (stem[5:] if stem.startswith("test_") else stem)
    if not flow_name:
        fail("init requires --flow (or a diagnose test filename that yields one)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", flow_name):
        fail("flow must use only letters, digits, underscores, and hyphens")

    current_phase = 4 if mode == "diagnose" else 1
    requirement = "" if mode == "diagnose" else str(SESSION_REQUIREMENT)
    test_dir = _config_value("test_dir") or "AutomationTests"
    expected_test = test_file or f"{test_dir}/tests/test_{flow_name}.py"
    data = {
        "run_id": str(uuid.uuid4()),
        "current_phase": current_phase,
        "phase_status": "IN_PROGRESS",
        "platform": platform,
        "build_policy": build_policy,
        "reset_policy": reset_policy,
        "flow_name": flow_name,
        "mode": mode,
        "code_map": {
            "entry_points": args.entry_points,
            "screens": args.screens,
            "source_files": [],
        },
        "artifacts": {
            "session_requirement": requirement,
            "flow_note": f".agentqa/memory/flows/{flow_name}.md",
            "screens_dir": ".agentqa/memory/screens",
            "test_file": expected_test,
        },
        "completed_checks": [],
        "blocker": None,
        "failures_baseline": [],
    }
    _write(path, data)
    print(f"Checkpoint created: {path}")
    print(f"Run ID: {data['run_id']}")
    print(f"Mode: {mode}; phase: {current_phase}")


def cmd_status(args: argparse.Namespace) -> None:
    print(json.dumps(_read(args.path), indent=2, ensure_ascii=False))


def cmd_record_check(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "record-check")
    phase = data.get("current_phase")
    allowed = PHASE_CHECKS.get(phase, set())
    if args.check not in allowed:
        fail(f"check {args.check!r} is not valid for phase {phase}; expected {sorted(allowed)}")
    _clear_token(data)
    _upsert_check(data, args.check, args.evidence)
    _write(args.path, data)
    print(f"Recorded check: {args.check}")


def cmd_record_code_map(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "record-code-map")
    if data.get("current_phase") != 1:
        fail("record-code-map is only valid in phase 1")
    code_map = data.setdefault("code_map", {})
    if args.entry_points is not None:
        code_map["entry_points"] = args.entry_points
    if args.screens is not None:
        code_map["screens"] = args.screens
    if args.source_files is not None:
        code_map["source_files"] = args.source_files
    _clear_token(data)
    _write(args.path, data)
    print(
        "Recorded code map: "
        f"{len(code_map.get('entry_points', []))} entry point(s), "
        f"{len(code_map.get('screens', []))} screen(s), "
        f"{len(code_map.get('source_files', []))} source file(s)"
    )


def cmd_set_blocker(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "set-blocker")
    if data.get("current_phase") != 3:
        fail("set-blocker is only valid in phase 3")
    _clear_token(data)
    data["phase_status"] = "WAITING_FOR_USER"
    data["blocker"] = args.blocker
    _write(args.path, data)
    print(f"Blocker set: {args.blocker}")


def cmd_clear_blocker(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "WAITING_FOR_USER", "clear-blocker")
    if data.get("current_phase") != 3 or not data.get("blocker"):
        fail("clear-blocker requires an active phase-3 blocker")
    _clear_token(data)
    data["phase_status"] = "IN_PROGRESS"
    data["blocker"] = None
    _write(args.path, data)
    print("Blocker cleared; phase 3 is IN_PROGRESS")


def cmd_set_failures_baseline(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "set-failures-baseline")
    if data.get("current_phase") != 2:
        fail("set-failures-baseline is only valid in phase 2")
    failures = Path(".agentqa/memory/failures")
    data["failures_baseline"] = sorted(p.name for p in failures.iterdir()) if failures.is_dir() else []
    _clear_token(data)
    _write(args.path, data)
    print(f"Failures baseline saved: {len(data['failures_baseline'])} file(s)")


def cmd_route_to_identifiers(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "route-to-identifiers")
    if data.get("current_phase") != 4:
        fail("route-to-identifiers is only valid from phase 4")
    _clear_token(data)
    data["current_phase"] = 3
    data["completed_checks"] = []
    data["blocker"] = None
    _write(args.path, data)
    print("Routed to phase 3 for app-code/identifier repair")


def cmd_complete(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "IN_PROGRESS", "complete")
    phase = data.get("current_phase")
    missing = PHASE_CHECKS.get(phase, set()) - set(_checks(data))
    if missing:
        fail(f"phase {phase} cannot complete; missing checks: {sorted(missing)}")
    _clear_token(data)
    data["phase_status"] = "COMPLETE"
    data["blocker"] = None
    _write(args.path, data)
    print(f"Phase {phase} marked COMPLETE")


def _run_memory_lint(errors: List[str]) -> None:
    lint = Path(__file__).with_name("memory-lint.py")
    if not lint.is_file():
        errors.append(f"memory-lint.py not found at {lint}")
        return
    result = subprocess.run(
        [sys.executable, str(lint), ".agentqa/memory"],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        errors.append(f"memory-lint.py exited {result.returncode}: {detail[:300]}")


def _validate_requirement(path: Path, errors: List[str]) -> None:
    if not path.is_file():
        errors.append(f"session requirement not found: {path}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    for heading in ("## Request", "## Success", "## Failure", "## Blockers"):
        if heading not in text:
            errors.append(f"session requirement missing heading: {heading}")


def _validate_phase(data: dict, path: Path, pytest_ok: bool) -> List[str]:
    errors: List[str] = []
    phase = data.get("current_phase")
    checks = _checks(data)
    for name in PHASE_CHECKS.get(phase, set()):
        if not checks.get(name, {}).get("ok"):
            errors.append(f"check {name!r} not completed")

    if phase == 1:
        requirement = _artifact(data, "session_requirement")
        if not requirement:
            errors.append("session requirement artifact is empty")
        else:
            _validate_requirement(Path(requirement), errors)
        code_map = data.get("code_map", {})
        if not code_map.get("entry_points"):
            errors.append("code_map.entry_points is empty")
        if not code_map.get("source_files"):
            errors.append("code_map.source_files is empty")

    elif phase == 2:
        flow_file = Path(_artifact(data, "flow_note"))
        if not flow_file.is_file():
            errors.append(f"flow note not found: {flow_file}")
        screens_dir = Path(_artifact(data, "screens_dir"))
        flow_tag = f"#{data.get('flow_name', '')}"
        screen_notes = list(screens_dir.glob("*.md")) if screens_dir.is_dir() else []
        if not screen_notes:
            errors.append(f"no screen notes found under {screens_dir}")
        elif not any(flow_tag in p.read_text(encoding="utf-8", errors="replace") for p in screen_notes):
            errors.append(f"no screen note contains current-flow tag {flow_tag}")
        failures = Path(".agentqa/memory/failures")
        current = {p.name for p in failures.iterdir()} if failures.is_dir() else set()
        new_failures = current - set(data.get("failures_baseline", []))
        if new_failures:
            errors.append(f"phase 2 created failure notes without a grounded signature: {sorted(new_failures)}")
        _run_memory_lint(errors)

    elif phase == 3:
        result = subprocess.run(
            ["git", "diff", "--numstat", "--", "*.swift", "*.java", "*.kt", "*.xml"],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            errors.append(f"git diff failed: {(result.stderr or result.stdout).strip()[:200]}")
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) > 0:
                errors.append(f"app-code diff contains {parts[1]} deletion(s): {line}")
        if data.get("blocker"):
            errors.append(f"blocker still set: {data['blocker']}")
        flow_tag = f"#{data.get('flow_name', '')}"
        screens = Path(_artifact(data, "screens_dir"))
        if screens.is_dir():
            for note in screens.glob("*.md"):
                for line in note.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "added-unverified" in line and flow_tag in line:
                        errors.append(f"identifier remains added-unverified: {note.name}: {line[:120]}")

    elif phase == 4:
        test_file = Path(_artifact(data, "test_file"))
        if not test_file.is_file():
            errors.append(f"test file not found: {test_file}")
        if not pytest_ok:
            errors.append("targeted pytest did not pass in this turn")

    elif phase == 5:
        requirement = _artifact(data, "session_requirement")
        if requirement and not Path(requirement).is_file():
            errors.append(f"working requirement was deleted before finalize: {requirement}")
        if not path.is_file():
            errors.append("checkpoint was deleted before finalize")
        _run_memory_lint(errors)
    else:
        errors.append(f"unknown phase: {phase}")
    return errors


def cmd_validate(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "COMPLETE", "validate")
    errors = _validate_phase(data, args.path, args.pytest_ok)
    if errors:
        _clear_token(data)
        data["phase_status"] = "IN_PROGRESS"
        _write(args.path, data)
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
    data["validated_phase"] = data["current_phase"]
    _write(args.path, data)
    print(f"Phase {data['current_phase']} validation: PASS")


def cmd_advance(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "COMPLETE", "advance")
    phase = data.get("current_phase")
    if data.get("validated_phase") != phase:
        fail("advance requires a current validation token")
    if phase >= MAX_PHASE:
        fail("phase 5 must finalize, not advance")
    _clear_token(data)
    data["current_phase"] = phase + 1
    data["phase_status"] = "IN_PROGRESS"
    data["completed_checks"] = []
    data["blocker"] = None
    _write(args.path, data)
    print(f"Advanced to phase {data['current_phase']}")


def _delete_working_files(path: Path, data: dict) -> None:
    requirement = _artifact(data, "session_requirement")
    if requirement:
        req_path = Path(requirement)
        if req_path.exists():
            req_path.unlink()
            print(f"Deleted: {req_path}")
    if path.exists():
        path.unlink()
        print(f"Deleted: {path}")


def cmd_finalize(args: argparse.Namespace) -> None:
    data = _read(args.path)
    _require_status(data, "COMPLETE", "finalize")
    if data.get("current_phase") != MAX_PHASE:
        fail(f"finalize requires phase {MAX_PHASE}")
    if data.get("validated_phase") != MAX_PHASE:
        fail("finalize requires a current validation token")
    _delete_working_files(args.path, data)
    print("Working-layer cleanup complete")


def cmd_abort(args: argparse.Namespace) -> None:
    data = _read(args.path)
    print(f"Aborting run {data.get('run_id')}: {args.reason}")
    _delete_working_files(args.path, data)
    print("Working-layer cleanup complete")


def _csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, handler):
        child = sub.add_parser(name)
        child.add_argument("--path", type=Path, default=DEFAULT_PATH)
        child.set_defaults(handler=handler)
        return child

    init = command("init", cmd_init)
    init.add_argument("--mode", choices=["new", "diagnose"], default="new")
    init.add_argument("--flow", default="")
    init.add_argument("--test-file", type=Path)
    init.add_argument("--platform", choices=["ios", "android"])
    init.add_argument("--build-policy", choices=["human", "agent"])
    init.add_argument("--reset-policy", choices=["always", "never"])
    init.add_argument("--entry-points", type=_csv, default=[])
    init.add_argument("--screens", type=_csv, default=[])

    command("status", cmd_status)

    record = command("record-check", cmd_record_check)
    record.add_argument("--check", required=True)
    record.add_argument("--evidence", default="")

    code_map = command("record-code-map", cmd_record_code_map)
    code_map.add_argument("--entry-points", type=_csv)
    code_map.add_argument("--screens", type=_csv)
    code_map.add_argument("--source-files", type=_csv)

    blocker = command("set-blocker", cmd_set_blocker)
    blocker.add_argument("--blocker", required=True)

    command("clear-blocker", cmd_clear_blocker)
    command("set-failures-baseline", cmd_set_failures_baseline)
    command("route-to-identifiers", cmd_route_to_identifiers)
    command("complete", cmd_complete)

    validate = command("validate", cmd_validate)
    validate.add_argument("--pytest-ok", action="store_true")

    command("advance", cmd_advance)
    command("finalize", cmd_finalize)

    abort = command("abort", cmd_abort)
    abort.add_argument("--reason", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    _eval_log(raw)
    args = build_parser().parse_args(raw)
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
