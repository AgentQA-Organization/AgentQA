"""The allowlist that stops AgentQA's own writes from raising a dialog.

Two failure modes here are silent, which is why they get tests rather than care:
a Write(...) rule is accepted by Claude Code and never matched, and a careless
scaffold clobbers settings a project already depends on.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scaffold-permissions.sh"


def run(repo, *args):
    env = dict(os.environ, AGENTQA_PROJECT_ROOT=str(repo))
    return subprocess.run(["bash", str(SCRIPT)] + list(args),
                          capture_output=True, text=True, env=env)


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / ".agentqa").mkdir(parents=True)
    (tmp_path / ".agentqa" / "config.yml").write_text(
        "platform: ios\ntest_dir: AutomationTests\n", encoding="utf-8")
    return tmp_path


def settings(repo):
    return json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))


def test_scaffolds_the_two_allow_rules(repo):
    assert run(repo).returncode == 0
    allow = settings(repo)["permissions"]["allow"]
    assert "Edit(/.agentqa/**)" in allow
    assert "Edit(/AutomationTests/**)" in allow


def test_never_emits_a_write_rule(repo):
    """Claude Code accepts Write(path), warns at startup, and never matches it.
    The rule looks right and does nothing — only a test catches that."""
    run(repo)
    for rule in settings(repo)["permissions"]["allow"]:
        assert not rule.startswith("Write("), rule
        assert not rule.startswith("NotebookEdit("), rule


def test_uses_the_configured_test_dir(repo):
    (repo / ".agentqa" / "config.yml").write_text(
        "platform: android\ntest_dir: e2e/ui\n", encoding="utf-8")
    run(repo)
    assert "Edit(/e2e/ui/**)" in settings(repo)["permissions"]["allow"]


def test_merges_into_existing_settings(repo):
    """test-auto-mytv already has enabledPlugins here. Losing it would silently
    disable the user's plugins."""
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"agentqa": True}}), encoding="utf-8")
    run(repo)
    data = settings(repo)
    assert data["enabledPlugins"] == {"agentqa": True}
    assert "Edit(/.agentqa/**)" in data["permissions"]["allow"]


def test_keeps_existing_allow_rules(repo):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(xcrun *)"]}}), encoding="utf-8")
    run(repo)
    allow = settings(repo)["permissions"]["allow"]
    assert "Bash(xcrun *)" in allow
    assert "Edit(/.agentqa/**)" in allow


def test_is_idempotent(repo):
    run(repo)
    run(repo)
    allow = settings(repo)["permissions"]["allow"]
    assert allow.count("Edit(/.agentqa/**)") == 1


def test_check_mode_reports_a_missing_scaffold(repo):
    assert run(repo, "--check").returncode != 0


def test_check_mode_passes_after_scaffolding(repo):
    run(repo)
    assert run(repo, "--check").returncode == 0
