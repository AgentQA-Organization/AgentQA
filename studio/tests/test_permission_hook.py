"""The permission bridge's decisions, isolated from stdin, subprocesses and time.

The invariant every test here defends: the hook may only ever move a prompt from
the terminal into the browser. It must never answer one. So every path that is not
an explicit human click has to come out as ("", "", 0) — print nothing, exit 0,
leave the terminal dialog alone.
"""
import json
from datetime import datetime, timedelta, timezone

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
