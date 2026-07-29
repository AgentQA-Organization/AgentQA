import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "checkpoint.py"


def run(project, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=project,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def project(tmp_path):
    config = tmp_path / ".agentqa" / "config.yml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "platform: ios\n"
        "bundle_id: com.example.app\n"
        "test_dir: AutomationTests\n"
        "build:\n"
        "  policy: human\n"
        "reset_app_data: never\n"
        "appium:\n"
        "  port: 4723\n",
        encoding="utf-8",
    )
    for folder in ("flows", "screens", "failures"):
        (tmp_path / ".agentqa" / "memory" / folder).mkdir(parents=True, exist_ok=True)
    return tmp_path


def checkpoint(project):
    return project / ".agentqa" / "memory" / ".run-checkpoint.md"


def init_new(project, *extra):
    return run(project, "init", "--flow", "login", *extra)


def test_init_reads_nested_config_and_writes_canonical_artifacts(project):
    result = init_new(project, "--screens", "login,home")
    assert result.returncode == 0, result.stderr
    data = json.loads(checkpoint(project).read_text())
    assert data["platform"] == "ios"
    assert data["build_policy"] == "human"
    assert data["reset_policy"] == "never"
    assert data["code_map"]["screens"] == ["login", "home"]
    assert data["artifacts"]["session_requirement"].endswith(".session-requirement.md")
    assert "session_requirement_path" not in data
    assert data["next_action"] == "execute-phase-1"


def test_init_refuses_existing_checkpoint(project):
    assert init_new(project).returncode == 0
    result = init_new(project)
    assert result.returncode == 1
    assert "already exists" in result.stderr


def test_diagnose_mode_requires_existing_test_and_starts_phase_four(project):
    test_file = project / "AutomationTests" / "tests" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_login(): pass\n", encoding="utf-8")
    result = run(project, "init", "--mode", "diagnose", "--test-file", test_file)
    assert result.returncode == 0, result.stderr
    data = json.loads(checkpoint(project).read_text())
    assert data["current_phase"] == 4
    assert data["flow_name"] == "login"
    assert data["artifacts"]["session_requirement"] == ""
    assert data["artifacts"]["test_file"] == str(test_file)


def test_argparse_rejects_unknown_option(project):
    result = run(project, "init", "--flow", "login", "--platfrom", "ios")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_record_code_map_and_checks_are_upserted(project):
    assert init_new(project).returncode == 0
    result = run(
        project,
        "record-code-map",
        "--entry-points",
        "intro,profile",
        "--screens",
        "login,home",
        "--source-files",
        "Login.swift,Home.swift",
    )
    assert result.returncode == 0, result.stderr
    assert run(project, "record-check", "--check", "source_read", "--evidence", "first").returncode == 0
    assert run(project, "record-check", "--check", "source_read", "--evidence", "updated").returncode == 0
    data = json.loads(checkpoint(project).read_text())
    source = [c for c in data["completed_checks"] if c["name"] == "source_read"]
    assert source == [{"name": "source_read", "evidence": "updated", "ok": True}]


def test_complete_requires_all_phase_checks(project):
    assert init_new(project).returncode == 0
    result = run(project, "complete")
    assert result.returncode == 1
    assert "missing checks" in result.stderr
    assert json.loads(checkpoint(project).read_text())["phase_status"] == "IN_PROGRESS"


def _ready_phase_one(project):
    init_new(project)
    requirement = project / ".agentqa" / "memory" / ".session-requirement.md"
    requirement.write_text(
        "## Request\nlogin\n## Success\nhome\n## Failure\nerror\n## Blockers\nnone\n",
        encoding="utf-8",
    )
    run(
        project,
        "record-code-map",
        "--entry-points",
        "intro",
        "--screens",
        "login,home",
        "--source-files",
        "Login.swift",
    )
    for name in ("codegraph_indexed", "source_read", "clarification_done"):
        assert run(project, "record-check", "--check", name, "--evidence", "ok").returncode == 0


def test_validate_token_is_required_for_advance(project):
    _ready_phase_one(project)
    assert run(project, "complete").returncode == 0
    assert run(project, "advance").returncode == 1
    assert run(project, "validate").returncode == 0
    data = json.loads(checkpoint(project).read_text())
    assert data["validated_phase"] == 1
    assert data["next_action"] == "controller-advance"
    assert run(project, "advance").returncode == 0
    data = json.loads(checkpoint(project).read_text())
    assert data["current_phase"] == 2
    assert data["completed_checks"] == []
    assert "validated_phase" not in data


def test_failed_validation_reopens_same_phase(project):
    assert init_new(project).returncode == 0
    for name in ("codegraph_indexed", "source_read", "clarification_done"):
        run(project, "record-check", "--check", name)
    assert run(project, "complete").returncode == 0
    result = run(project, "validate")
    assert result.returncode == 1
    data = json.loads(checkpoint(project).read_text())
    assert data["current_phase"] == 1
    assert data["phase_status"] == "IN_PROGRESS"


def test_human_build_blocker_cannot_complete(project):
    assert init_new(project).returncode == 0
    data = json.loads(checkpoint(project).read_text())
    data["current_phase"] = 3
    checkpoint(project).write_text(json.dumps(data), encoding="utf-8")
    assert run(project, "set-blocker", "--blocker", "WAITING_FOR_HUMAN_BUILD").returncode == 0
    assert run(project, "complete").returncode == 1
    assert run(project, "clear-blocker").returncode == 0
    data = json.loads(checkpoint(project).read_text())
    assert data["phase_status"] == "IN_PROGRESS"
    assert data["blocker"] is None


def test_phase_four_routes_to_identifiers(project):
    test_file = project / "AutomationTests" / "tests" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_login(): pass\n", encoding="utf-8")
    assert run(project, "init", "--mode", "diagnose", "--test-file", test_file).returncode == 0
    assert run(project, "route-to-identifiers").returncode == 0
    data = json.loads(checkpoint(project).read_text())
    assert data["current_phase"] == 3
    assert data["phase_status"] == "IN_PROGRESS"


def test_phase_five_cannot_advance_and_finalize_cleans_working_files(project):
    assert init_new(project).returncode == 0
    requirement = project / ".agentqa" / "memory" / ".session-requirement.md"
    requirement.write_text("working\n", encoding="utf-8")
    data = json.loads(checkpoint(project).read_text())
    data.update(current_phase=5, phase_status="COMPLETE", validated_phase=5)
    checkpoint(project).write_text(json.dumps(data), encoding="utf-8")
    assert run(project, "advance").returncode == 1
    assert run(project, "finalize").returncode == 0
    assert not checkpoint(project).exists()
    assert not requirement.exists()


def test_abort_cleans_diagnosis_checkpoint(project):
    test_file = project / "AutomationTests" / "tests" / "test_login.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_login(): pass\n", encoding="utf-8")
    assert run(project, "init", "--mode", "diagnose", "--test-file", test_file).returncode == 0
    assert run(project, "abort", "--reason", "real app failure").returncode == 0
    assert not checkpoint(project).exists()


def test_eval_log_uses_structured_schema(project, monkeypatch):
    state = project / "eval-state"
    monkeypatch.setenv("AGENTQA_EVAL_STATE", str(state))
    assert init_new(project).returncode == 0
    calls = [json.loads(line) for line in (state / "calls.jsonl").read_text().splitlines()]
    assert calls[0]["tool"] == "checkpoint.py"
    assert calls[0]["argv"][0] == "init"
