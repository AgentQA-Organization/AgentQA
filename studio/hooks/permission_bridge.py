#!/usr/bin/env python3
"""Route a Claude Code permission dialog to the Studio dashboard.

Claude Code fires PermissionRequest only when it is about to interrupt the user.
When a Studio agent is attached to this repo, that interruption belongs in the
browser the tester is already watching, not in a terminal they are not.

The one rule this file exists to keep: it may move a prompt, never answer one.
Every path that is not an explicit human click prints nothing and exits 0, which
leaves Claude Code's own dialog exactly as it would have been.
"""
import json
from datetime import datetime, timezone

# The heartbeat only bumps when the agent posts or waits, so it goes quiet for
# the length of a tool call. The window has to outlast a slow build or a long
# exploration, while still letting a crashed session stop swallowing prompts.
HEARTBEAT_MAX_AGE_S = 900
DIFF_LIMIT = 2000
DEFAULT_REJECT_REASON = "Rejected from the AgentQA Studio dashboard."

_ALLOW = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                 "decision": {"behavior": "allow"}}}
_DEFER = ("", "", 0)


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def should_bridge(state, now=None):
    """True when a live Studio connector is there to show the card to."""
    if not isinstance(state, dict):
        return False
    if not state.get("attached") or not state.get("connector_id"):
        return False
    stamped = _parse_ts(state.get("heartbeat_ts"))
    if stamped is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - stamped).total_seconds() <= HEARTBEAT_MAX_AGE_S


def _clip(text):
    text = "" if text is None else str(text)
    if len(text) <= DIFF_LIMIT:
        return text
    return text[:DIFF_LIMIT] + "\n… (truncated)"


def describe_tool(tool_name, tool_input):
    """A prompt line and a body the tester can judge without opening a terminal."""
    data = tool_input if isinstance(tool_input, dict) else {}
    path = data.get("file_path") or data.get("notebook_path") or ""
    if tool_name == "Edit":
        return ("Agent wants to edit %s" % (path or "a file"),
                _clip("- %s\n+ %s" % (data.get("old_string", ""),
                                      data.get("new_string", ""))))
    if tool_name == "Write":
        return ("Agent wants to write %s" % (path or "a file"),
                _clip(data.get("content", "")))
    if tool_name == "Bash":
        return ("Agent wants to run a command", _clip(data.get("command", "")))
    return ("Agent wants to use %s" % tool_name,
            _clip(json.dumps(data, ensure_ascii=False, indent=2)))


def decide_output(wait_result):
    """Map studio-wait.py's result to (stdout, stderr, exit_code).

    Reject leaves through exit 2 rather than a {"behavior": "deny"} payload
    because PermissionRequest's decision object has no reason field, and stderr
    is the documented channel for a blocking reason. Losing the tester's note
    would make the agent ask a question they just answered.
    """
    if not isinstance(wait_result, dict):
        return _DEFER
    if wait_result.get("status") != "answered":
        return _DEFER
    record = wait_result.get("record")
    if not isinstance(record, dict):
        return _DEFER
    decision = record.get("decision")
    if decision == "approve":
        return (json.dumps(_ALLOW), "", 0)
    if decision == "reject":
        note = (str(record.get("note") or "")).strip() or DEFAULT_REJECT_REASON
        return ("", note, 2)
    return _DEFER
