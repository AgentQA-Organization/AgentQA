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
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The heartbeat only bumps when the agent posts or waits, so it goes quiet for
# the length of a tool call. The window has to outlast a slow build or a long
# exploration, while still letting a crashed session stop swallowing prompts.
HEARTBEAT_MAX_AGE_S = 900
DIFF_LIMIT = 2000
DEFAULT_REJECT_REASON = "Rejected from the AgentQA Studio dashboard."

# Resolve the connector scripts from the plugin root when the hook runs inside an
# installed plugin, and from the source tree otherwise, so the same file works in
# a checkout and in ~/.claude/plugins.
_PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT")
                    or Path(__file__).resolve().parents[2])
_SCRIPTS = _PLUGIN_ROOT / "skills" / "agentqa-studio" / "scripts"

# Same import pattern studio-post.py and studio-wait.py use for this module: it
# is stdlib-only and self-contained, so the restore in _restore_state below can
# call the real write_state() instead of hand-rolling a json.dump that would
# drift from the protocol.
sys.path.insert(0, str(_SCRIPTS))
import studio_common as sc

WAIT_TIMEOUT_S = 540      # under the hook's own 600s cap, so we return rather
                          # than get killed mid-wait

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
    if not state.get("attached"):
        return False
    connector_id = state.get("connector_id")
    if not isinstance(connector_id, str) or not connector_id:
        # A non-string id (a corrupt state.json, say) cannot match a live
        # connector anyway, and would otherwise crash subprocess.run once it
        # reaches _script() as an argv element.
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
    path = data.get("file_path") or ""
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


def _read_state(repo):
    path = Path(repo) / ".agentqa" / "studio" / "state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _script(name, *args):
    out = subprocess.run([sys.executable, str(_SCRIPTS / name)] + list(args),
                         capture_output=True, text=True)
    return out


def _restore_state(repo, connector, status, awaiting):
    """Put status/awaiting back to what they were before this card was posted.

    studio-post.py's `question` post flips state.json to status="waiting",
    awaiting=<qid> and nothing else ever restores it — the mailbox is built for
    the agent's own checkpoints, where the connector script that posted the
    question is also the one that later posts a `result` and clears it. This
    hook has no such follow-up call, so once the card is resolved (approved,
    rejected, timed out, or an unparseable wait result — the card is finished
    in all of them) it must put the prior values back itself, or the dashboard
    reads "waiting on you" for an agent that is back to working.

    Best-effort and silent on purpose: the human's decision (or the fallback to
    the terminal dialog) already happened and must reach its outcome regardless
    of whether this bookkeeping succeeds, so every exception here — including
    Superseded, which write_state raises when another connector has since taken
    the mailbox over, and which must simply not be restored into — is
    swallowed rather than allowed to change the return value or crash the hook.
    """
    try:
        sc.write_state(repo, connector=connector, status=status, awaiting=awaiting)
    except Exception:
        pass


def main(stdin=None):
    try:
        return _main(stdin)
    except Exception:
        # A safety net, not a substitute for the guards above: for this hook,
        # falling back to Claude Code's own dialog is the only acceptable
        # failure mode, so an error none of the targeted checks anticipated
        # must still end in silence rather than an uncaught traceback that
        # would otherwise leave the terminal's prompt in an undefined state.
        return 0


def _main(stdin):
    raw = (stdin or sys.stdin).read()
    try:
        event = json.loads(raw)
    except ValueError:
        return 0                       # not our shape — leave the dialog alone
    repo = event.get("cwd") if isinstance(event, dict) else None
    if not isinstance(repo, str) or not repo:
        # A missing or wrong-typed cwd (e.g. a number) would otherwise reach
        # Path(repo) in _read_state and raise TypeError.
        repo = os.getcwd()
    state = _read_state(repo)
    if not should_bridge(state):
        return 0
    connector = state.get("connector_id")
    prior_status = state.get("status")
    prior_awaiting = state.get("awaiting")

    prompt, diff = describe_tool(event.get("tool_name") or "a tool",
                                 event.get("tool_input"))
    posted = _script("studio-post.py", str(repo), "question",
                     "--kind", "review", "--subtype", "permission",
                     "--prompt", prompt, "--diff", diff,
                     "--connector", connector)
    if posted.returncode != 0:         # superseded (3) or a broken mailbox
        return 0
    try:
        qid = posted.stdout.strip()
        if not qid:
            return 0

        waited = _script("studio-wait.py", str(repo), "--reply-to", qid,
                         "--timeout", str(WAIT_TIMEOUT_S), "--connector", connector)
        try:
            result = json.loads(waited.stdout.strip() or "{}")
        except ValueError:
            result = {}

        out, err, code = decide_output(result)
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        return code
    finally:
        # The post above succeeded, so it did flip state.json to waiting/awaiting
        # — every path from here on (early return for a blank qid, or any of
        # decide_output's outcomes) must restore it.
        _restore_state(repo, connector, prior_status, prior_awaiting)


if __name__ == "__main__":
    sys.exit(main())
