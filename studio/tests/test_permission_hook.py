"""The permission bridge's decisions, isolated from stdin, subprocesses and time.

The invariant every test here defends: the hook may only ever move a prompt from
the terminal into the browser. It must never answer one. So every path that is not
an explicit human click has to come out as ("", "", 0) — print nothing, exit 0,
leave the terminal dialog alone.
"""
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from studio.hooks.permission_bridge import (
    DEFAULT_REJECT_REASON, DIFF_LIMIT, HEARTBEAT_MAX_AGE_S,
    decide_output, describe_tool, should_bridge,
)

NOW = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)


def state(**over):
    base = {"v": 1, "attached": True, "connector_id": "c1",
            "heartbeat_ts": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
    base.update(over)
    return base


# ---- should_bridge: when is a browser actually listening? -----------------

def test_bridges_when_a_connector_is_attached():
    assert should_bridge(state(), now=NOW) is True


def test_no_bridge_without_a_mailbox():
    """No .agentqa/studio at all — an ordinary repo. read_state returns {}."""
    assert should_bridge({}, now=NOW) is False


def test_no_bridge_when_detached():
    assert should_bridge(state(attached=False), now=NOW) is False


def test_no_bridge_without_a_connector_id():
    assert should_bridge(state(connector_id=None), now=NOW) is False


def test_no_bridge_when_the_heartbeat_is_long_dead():
    """A crashed session leaves attached:true behind. Without this the repo would
    stall for the full wait on every prompt, forever."""
    old = NOW - timedelta(seconds=HEARTBEAT_MAX_AGE_S + 60)
    assert should_bridge(state(heartbeat_ts=old.strftime("%Y-%m-%dT%H:%M:%SZ")),
                         now=NOW) is False


def test_bridges_while_the_agent_is_busy_in_a_long_tool_call():
    """The heartbeat only bumps when the agent posts or waits. During a long
    exploration it goes quiet for minutes — and that is exactly when writes
    happen, so the window must be generous enough to survive it."""
    quiet = NOW - timedelta(seconds=HEARTBEAT_MAX_AGE_S - 60)
    assert should_bridge(state(heartbeat_ts=quiet.strftime("%Y-%m-%dT%H:%M:%SZ")),
                         now=NOW) is True


def test_no_bridge_on_a_malformed_heartbeat():
    assert should_bridge(state(heartbeat_ts="not-a-timestamp"), now=NOW) is False


def test_no_bridge_on_a_missing_heartbeat():
    assert should_bridge(state(heartbeat_ts=None), now=NOW) is False


# ---- describe_tool: what the tester reads on the card --------------------

def test_edit_names_the_file_and_shows_both_sides():
    prompt, diff = describe_tool("Edit", {
        "file_path": "/repo/Sources/Home.swift",
        "old_string": "let a = 1", "new_string": "let a = 2"})
    assert "Home.swift" in prompt
    assert "let a = 1" in diff and "let a = 2" in diff


def test_write_names_the_file_and_previews_the_content():
    prompt, diff = describe_tool("Write", {
        "file_path": "/repo/tests/test_login.py", "content": "import pytest\n"})
    assert "test_login.py" in prompt
    assert "import pytest" in diff


def test_bash_shows_the_command():
    prompt, diff = describe_tool("Bash", {"command": "rm -rf build"})
    assert "rm -rf build" in diff


def test_unknown_tool_still_produces_a_readable_card():
    """A tool the bridge has never seen must not render an empty card — a blank
    prompt is worse than a crude one, because the tester cannot judge it."""
    prompt, diff = describe_tool("MysteryTool", {"weird": "payload"})
    assert "MysteryTool" in prompt
    assert "payload" in diff


def test_long_content_is_truncated():
    _, diff = describe_tool("Write", {"file_path": "/a.txt", "content": "x" * 9000})
    assert len(diff) <= DIFF_LIMIT + 100        # +slack for the truncation marker


def test_missing_fields_do_not_raise():
    prompt, diff = describe_tool("Edit", {})
    assert isinstance(prompt, str) and isinstance(diff, str)


# ---- decide_output: the only place an exit code is chosen ----------------

def test_approve_allows_on_exit_zero():
    out, err, code = decide_output(
        {"status": "answered", "record": {"decision": "approve"}})
    assert code == 0 and err == ""
    assert json.loads(out)["hookSpecificOutput"] == {
        "hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}


def test_reject_denies_via_exit_two_and_carries_the_note():
    out, err, code = decide_output({"status": "answered", "record": {
        "decision": "reject", "note": "use the page object instead"}})
    assert code == 2
    assert out == ""
    assert "use the page object instead" in err


def test_reject_without_a_note_still_gives_a_reason():
    _, err, code = decide_output(
        {"status": "answered", "record": {"decision": "reject"}})
    assert code == 2 and err.strip() == DEFAULT_REJECT_REASON


def test_reject_with_non_string_note_does_not_raise():
    """Non-string notes reach here via POST /api/studio/reply (studio/server.py:164-171)
    which spreads the request payload into the reply record unvalidated. protocol.validate()
    checks reply_to but never checks note's type. This is a real path, not hypothetical."""
    _, err, code = decide_output(
        {"status": "answered", "record": {"decision": "reject", "note": 123}})
    assert code == 2 and isinstance(err, str)


def test_timeout_defers_to_the_terminal():
    assert decide_output({"status": "waiting"}) == ("", "", 0)


def test_supersede_defers_to_the_terminal():
    assert decide_output({"status": "superseded", "connector_id": "c2"}) == ("", "", 0)


def test_unknown_decision_defers_rather_than_guessing():
    """A reply shape the bridge does not understand must not become an allow."""
    assert decide_output(
        {"status": "answered", "record": {"decision": "maybe"}}) == ("", "", 0)


def test_garbage_wait_result_defers():
    assert decide_output({}) == ("", "", 0)


# ---- end to end, through a real mailbox ----------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "agentqa-studio" / "scripts"


@pytest.fixture()
def attached_repo(tmp_path):
    """A repo whose mailbox looks like a live /agentqa-studio session."""
    sys.path.insert(0, str(SCRIPTS))
    import studio_common as sc
    sc.reset_state(tmp_path, connector_id="c1", status="running")
    return tmp_path


def _answer_when_asked(repo, decision, note=None, timeout=20):
    """Play the browser: wait for the card, then post the reply the tester would."""
    sys.path.insert(0, str(SCRIPTS))
    import studio_common as sc

    def run():
        deadline = time.time() + timeout
        while time.time() < deadline:
            for rec in sc.read_jsonl(sc.studio_dir(repo) / "outbox.jsonl"):
                if rec.get("type") == "question" and rec.get("subtype") == "permission":
                    reply = {"v": 1, "id": sc.new_id(), "ts": sc.now_ts(),
                             "type": "reply", "reply_to": rec["id"],
                             "decision": decision}
                    if note:
                        reply["note"] = note
                    sc.append_line(sc.studio_dir(repo) / "inbox.jsonl", reply)
                    return
            time.sleep(0.05)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def _run_hook(repo, payload):
    return subprocess.run(
        [sys.executable, "-m", "studio.hooks.permission_bridge"],
        input=json.dumps(payload), capture_output=True, text=True,
        cwd=str(REPO_ROOT))


def test_approve_end_to_end(attached_repo):
    _answer_when_asked(attached_repo, "approve")
    out = _run_hook(attached_repo, {
        "hook_event_name": "PermissionRequest", "cwd": str(attached_repo),
        "tool_name": "Edit",
        "tool_input": {"file_path": "Home.swift",
                       "old_string": "a", "new_string": "b"}})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_reject_end_to_end_carries_the_note(attached_repo):
    _answer_when_asked(attached_repo, "reject", note="edit the page object")
    out = _run_hook(attached_repo, {
        "hook_event_name": "PermissionRequest", "cwd": str(attached_repo),
        "tool_name": "Edit",
        "tool_input": {"file_path": "Home.swift",
                       "old_string": "a", "new_string": "b"}})
    assert out.returncode == 2
    assert out.stdout == ""
    assert "edit the page object" in out.stderr


def test_card_reaches_the_outbox(attached_repo):
    _answer_when_asked(attached_repo, "approve")
    _run_hook(attached_repo, {
        "hook_event_name": "PermissionRequest", "cwd": str(attached_repo),
        "tool_name": "Write",
        "tool_input": {"file_path": "t.py", "content": "import pytest"}})
    sys.path.insert(0, str(SCRIPTS))
    import studio_common as sc
    cards = [r for r in sc.read_jsonl(sc.studio_dir(attached_repo) / "outbox.jsonl")
             if r.get("subtype") == "permission"]
    assert len(cards) == 1
    assert "t.py" in cards[0]["prompt"]
    assert "import pytest" in cards[0]["diff"]


def test_unattached_repo_is_silent(tmp_path):
    """The common case for every repo that never runs Studio: print nothing,
    exit 0, let the terminal dialog happen."""
    out = _run_hook(tmp_path, {
        "hook_event_name": "PermissionRequest", "cwd": str(tmp_path),
        "tool_name": "Write", "tool_input": {"file_path": "x", "content": "y"}})
    assert (out.returncode, out.stdout, out.stderr) == (0, "", "")


def test_malformed_stdin_is_silent(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "studio.hooks.permission_bridge"],
        input="not json", capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert (out.returncode, out.stdout) == (0, "")
