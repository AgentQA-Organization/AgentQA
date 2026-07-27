# Studio Permission Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Claude Code's own permission dialogs to the AgentQA Studio dashboard, so a tester driving a run from the browser is never blocked by a prompt that exists only in the terminal.

**Architecture:** A plugin-level `PermissionRequest` hook fires only when a dialog would appear. It reads `.agentqa/studio/state.json` at the session's cwd; if a Studio agent is attached it posts a `permission` card through the existing `studio-post.py`, blocks on `studio-wait.py`, and converts the tester's click into a decision. Approve leaves as JSON on exit 0; reject leaves as exit 2 with the note on stderr. Every other path prints nothing, which leaves the terminal dialog exactly as it is today.

**Tech Stack:** Python 3.9 stdlib only; existing Studio Protocol v1 mailbox; vanilla-JS dashboard; pytest.

**Spec:** [`docs/superpowers/specs/2026-07-27-studio-permission-bridge-design.md`](../specs/2026-07-27-studio-permission-bridge-design.md)

## Global Constraints

- **Python 3.9.6.** No `match`, no PEP-604 (`int | None`) annotations evaluated at runtime. The venv is `.devvenv/bin/python`.
- **Stdlib only** in `studio/hooks/` and `skills/agentqa-studio/scripts/`, matching `studio_common.py`'s existing contract ("Stdlib only, self-contained").
- **The hook never emits `allow` without a human click.** Every guard, error, and timeout path prints nothing to stdout and exits 0.
- **Protocol changes land in three places at once**, or the suite goes red: `studio/protocol.py` (`QUESTION_SUBTYPES`), `skills/agentqa-studio/scripts/studio-post.py` (argparse `choices`), and `studio/protocol_v1.json` (the canonical fixture both halves validate against).
- **Permission rules use `Edit(...)`, never `Write(...)`.** Claude Code's file permission checks match only `Edit(path)` and `Read(path)`; a `Write(path)` rule is accepted, warned about at startup, and never matched.
- **Run the suite with** `.devvenv/bin/python -m pytest studio/tests skills/agentqa-studio/tests -q` (170 passing at plan time).

---

## File Structure

| File | Responsibility |
|---|---|
| `studio/hooks/__init__.py` (create) | package marker |
| `studio/hooks/permission_bridge.py` (create) | the hook: pure decision helpers + a thin I/O `main()` |
| `studio/tests/test_permission_hook.py` (create) | unit tests for the pure helpers, plus one end-to-end mailbox pass |
| `hooks/hooks.json` (create) | plugin-level `PermissionRequest` registration |
| `studio/protocol.py` (modify) | add `permission` to `QUESTION_SUBTYPES` |
| `studio/protocol_v1.json` (modify) | add a `question_permission` fixture |
| `studio/static/app.js` (modify) | add `permission` to `CARD_SUBTYPE_LABEL` |
| `skills/agentqa-studio/scripts/studio-post.py` (modify) | accept `--subtype permission` |
| `skills/agentqa-init/scripts/scaffold-permissions.sh` (create) | merge the allowlist into `<repo>/.claude/settings.json` |
| `skills/agentqa-init/tests/test_scaffold_permissions.py` (create) | asserts `Edit(` form and non-destructive merge |
| `skills/agentqa-init/references/init.md` (modify) | document the new scaffold step |
| `docs/agentqa-studio.md` (modify) | document the Permission card |

The hook splits into pure helpers (`describe_tool`, `should_bridge`, `decide_output`) and a `main()` that does subprocess and I/O. The helpers hold all the decisions and are the entire test surface; `main()` is wiring thin enough to read at a glance. This mirrors how `studio/tests/test_convo_render.py` tests UI decisions by slicing pure functions out of `app.js`.

---

## Task 1: Spike — does a rejection reason reach the model?

The spec's one open question. Everything else is unaffected by the answer, but the fallback in Task 6 depends on it, so settle it before building. This task is a manual experiment, not TDD; nothing is committed except the recorded answer.

**Files:**
- Create: `/tmp/spike-hook.sh` (throwaway)
- Modify: `docs/superpowers/specs/2026-07-27-studio-permission-bridge-design.md` (record the result)

- [ ] **Step 1: Write a throwaway hook that always rejects with a sentinel**

```bash
cat > /tmp/spike-hook.sh <<'EOF'
#!/usr/bin/env bash
echo "SPIKE_SENTINEL_7Q2X the tester said: use a different file" >&2
exit 2
EOF
chmod +x /tmp/spike-hook.sh
```

- [ ] **Step 2: Register it in a scratch repo**

```bash
mkdir -p /tmp/spike-repo/.claude && cd /tmp/spike-repo
git init -q 2>/dev/null || true
cat > .claude/settings.json <<'EOF'
{
  "hooks": {
    "PermissionRequest": [
      { "matcher": "*", "hooks": [ { "type": "command", "command": "/tmp/spike-hook.sh" } ] }
    ]
  }
}
EOF
```

- [ ] **Step 3: Run a session that triggers a file write**

Start Claude Code in `/tmp/spike-repo` and ask it to create a file, e.g. *"create a file notes.txt containing hello"*. The write must not be pre-allowed, so do not add any `Edit(...)` allow rule.

- [ ] **Step 4: Observe two things and record them**

1. Was the tool call denied? (Expected yes — the exit-code table documents `PermissionRequest` + exit 2 as "Denies the permission".)
2. Did the string `SPIKE_SENTINEL_7Q2X` appear in what the agent said back? Grep the transcript to be sure rather than trusting the rendered output:

```bash
grep -rl SPIKE_SENTINEL_7Q2X ~/.claude/projects/-tmp-spike-repo/ 2>/dev/null
```

- [ ] **Step 5: Record the answer in the spec**

Replace the "Spike this first" paragraph with what was observed. If the sentinel reached the model, delete the "If stderr does not reach the model" fallback paragraph and drop Task 6 from this plan. If it did not, keep both.

- [ ] **Step 6: Clean up and commit the spec**

```bash
rm -rf /tmp/spike-repo /tmp/spike-hook.sh
git add docs/superpowers/specs/2026-07-27-studio-permission-bridge-design.md
git commit -m "docs(studio): record permission-bridge spike result"
```

---

## Task 2: The `permission` subtype and its card label

**Files:**
- Modify: `studio/protocol.py:17`
- Modify: `studio/protocol_v1.json`
- Modify: `studio/static/app.js` (`CARD_SUBTYPE_LABEL`)
- Modify: `skills/agentqa-studio/scripts/studio-post.py:46-47`
- Test: `studio/tests/test_protocol.py`, `studio/tests/test_convo_render.py` (existing, will fail first)

**Interfaces:**
- Produces: a `question` record with `kind: "review"`, `subtype: "permission"`, optional `diff`. Tasks 3–5 post exactly this shape.

- [ ] **Step 1: Write the failing test**

Append to `studio/tests/test_protocol.py`. The file already does
`from studio import protocol` at the top, so call it through the module — there is
no bare `validate` name in scope:

```python
def test_permission_subtype_is_valid():
    """The permission bridge posts questions with this subtype; validate() must
    accept them or the hook's post is rejected at the mailbox boundary."""
    rec = {"v": 1, "id": "qp", "ts": "2026-07-27T00:00:00Z", "type": "question",
           "kind": "review", "subtype": "permission",
           "prompt": "Agent wants to edit Home.swift"}
    assert protocol.validate(rec) is rec
```

- [ ] **Step 2: Run it and the existing label-consistency test**

Run: `.devvenv/bin/python -m pytest studio/tests/test_protocol.py::test_permission_subtype_is_valid -v`
Expected: FAIL — `ProtocolError: question subtype invalid: 'permission'`

- [ ] **Step 3: Add the subtype in all three places**

`studio/protocol.py` line 17:

```python
QUESTION_SUBTYPES = frozenset({"clarify", "ask", "build", "review", "permission"})
```

`skills/agentqa-studio/scripts/studio-post.py` lines 46-47:

```python
    q.add_argument("--subtype", required=True,
                   choices=["clarify", "ask", "build", "review", "permission"])
```

`studio/protocol_v1.json` — inside the top-level `"outbox"` object, after the
`question_ask` entry, matching the existing one-record-per-line style. The
existing `test_validate_accepts_every_fixture_record` walks every record in that
object, so this entry is validated the moment it is added:

```json
    "question_permission": {"v": 1, "id": "qp", "ts": "2026-07-25T10:03:00Z", "type": "question", "kind": "review", "subtype": "permission", "prompt": "Agent wants to edit app source: Sources/HomeViewController.swift", "diff": "- title.text = \"Home\"\n+ title.text = \"Home\"\n+ title.accessibilityIdentifier = \"home_title\""},
```

- [ ] **Step 4: Run the protocol test — and watch the label test go red**

Run: `.devvenv/bin/python -m pytest studio/tests/test_protocol.py studio/tests/test_convo_render.py -q`
Expected: the protocol test PASSES; `test_every_protocol_subtype_has_a_label` now FAILS with `question subtypes with no card label: ['permission']`. That guard firing is the point — it was written for this class of bug.

- [ ] **Step 5: Add the label**

`studio/static/app.js`, in the `CARD_SUBTYPE_LABEL` declaration:

```js
const CARD_SUBTYPE_LABEL = { clarify: "Clarify", ask: "System dialog", build: "Build step", review: "Review", permission: "Permission" };
```

- [ ] **Step 6: Run the full suite**

Run: `.devvenv/bin/python -m pytest studio/tests skills/agentqa-studio/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add studio/protocol.py studio/protocol_v1.json studio/static/app.js \
        skills/agentqa-studio/scripts/studio-post.py studio/tests/test_protocol.py
git commit -m "feat(studio): add the permission question subtype and its card label"
```

---

## Task 3: The hook's pure decision helpers

**Files:**
- Create: `studio/hooks/__init__.py`, `studio/hooks/permission_bridge.py`
- Test: `studio/tests/test_permission_hook.py`

**Interfaces:**
- Produces, for Task 4:
  - `should_bridge(state, now=None) -> bool` — `state` is the parsed `state.json` dict (or `{}`), `now` a `datetime` for testing.
  - `describe_tool(tool_name, tool_input) -> (prompt: str, diff: str)`
  - `decide_output(wait_result) -> (stdout: str, stderr: str, exit_code: int)` — `wait_result` is the dict `studio-wait.py` printed.
  - Constants: `HEARTBEAT_MAX_AGE_S = 900`, `DIFF_LIMIT = 2000`, `DEFAULT_REJECT_REASON`.

- [ ] **Step 1: Write the failing tests**

Create `studio/tests/test_permission_hook.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'studio.hooks'`

- [ ] **Step 3: Write the implementation**

Create `studio/hooks/__init__.py` as an empty file. Create `studio/hooks/permission_bridge.py`:

```python
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
        note = (record.get("note") or "").strip() or DEFAULT_REJECT_REASON
        return ("", note, 2)
    return _DEFER
```

- [ ] **Step 4: Run to verify it passes**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add studio/hooks/__init__.py studio/hooks/permission_bridge.py \
        studio/tests/test_permission_hook.py
git commit -m "feat(studio): permission-bridge decision helpers"
```

---

## Task 4: The hook's I/O shell

**Files:**
- Modify: `studio/hooks/permission_bridge.py` (add `main()`)
- Test: `studio/tests/test_permission_hook.py` (append)

**Interfaces:**
- Consumes: `should_bridge`, `describe_tool`, `decide_output` from Task 3.
- Produces: `main(argv=None, stdin=None) -> int`, writing to `sys.stdout` / `sys.stderr`. Task 5's `hooks.json` invokes the module directly.

- [ ] **Step 1: Write the failing end-to-end test**

Append to `studio/tests/test_permission_hook.py`:

```python
# ---- end to end, through a real mailbox ----------------------------------

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q -k "end_to_end or silent or outbox"`
Expected: FAIL — the module has no `__main__` entry point yet.

- [ ] **Step 3: Add `main()` and the module entry point**

Append to `studio/hooks/permission_bridge.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

# Resolve the connector scripts from the plugin root when the hook runs inside an
# installed plugin, and from the source tree otherwise, so the same file works in
# a checkout and in ~/.claude/plugins.
_PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT")
                    or Path(__file__).resolve().parents[2])
_SCRIPTS = _PLUGIN_ROOT / "skills" / "agentqa-studio" / "scripts"

WAIT_TIMEOUT_S = 540      # under the hook's own 600s cap, so we return rather
                          # than get killed mid-wait


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


def main(argv=None, stdin=None):
    raw = (stdin or sys.stdin).read()
    try:
        event = json.loads(raw)
    except ValueError:
        return 0                       # not our shape — leave the dialog alone
    repo = event.get("cwd") or os.getcwd()
    state = _read_state(repo)
    if not should_bridge(state):
        return 0
    connector = state.get("connector_id")

    prompt, diff = describe_tool(event.get("tool_name") or "a tool",
                                 event.get("tool_input"))
    posted = _script("studio-post.py", str(repo), "question",
                     "--kind", "review", "--subtype", "permission",
                     "--prompt", prompt, "--diff", diff,
                     "--connector", connector)
    if posted.returncode != 0:         # superseded (3) or a broken mailbox
        return 0
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


if __name__ == "__main__":
    sys.exit(main())
```

Move the `import json` at the top of the file above these additions if the linter complains about ordering; the module keeps a single import block.

- [ ] **Step 4: Run the whole file**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the full suite for regressions**

Run: `.devvenv/bin/python -m pytest studio/tests skills/agentqa-studio/tests -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add studio/hooks/permission_bridge.py studio/tests/test_permission_hook.py
git commit -m "feat(studio): wire the permission bridge to the mailbox"
```

---

## Task 5: Register the hook with the plugin

**Files:**
- Create: `hooks/hooks.json`
- Test: `studio/tests/test_permission_hook.py` (append)

**Interfaces:**
- Consumes: `studio/hooks/permission_bridge.py` from Task 4.

- [ ] **Step 1: Write the failing test**

Append to `studio/tests/test_permission_hook.py`:

```python
# ---- plugin registration -------------------------------------------------

def test_plugin_registers_the_permission_hook():
    cfg = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entries = cfg["hooks"]["PermissionRequest"]
    assert entries, "PermissionRequest must be registered or the bridge never runs"
    command = entries[0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in command, \
        "an absolute path would break for every user but the author"
    assert "permission_bridge" in command


def test_hook_matcher_covers_every_tool():
    """PermissionRequest only fires when a dialog would appear, so narrowing by
    tool name would drop exactly the unusual prompts a watching tester needs."""
    cfg = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert cfg["hooks"]["PermissionRequest"][0]["matcher"] == "*"


def test_hook_timeout_outlasts_the_wait():
    """A hook killed mid-wait leaves the outcome to the harness. It has to be
    able to return its own answer."""
    from studio.hooks.permission_bridge import WAIT_TIMEOUT_S
    cfg = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert cfg["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"] > WAIT_TIMEOUT_S
```

- [ ] **Step 2: Run to verify it fails**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q -k "plugin or matcher or timeout"`
Expected: FAIL — `FileNotFoundError: hooks/hooks.json`

- [ ] **Step 3: Create the registration**

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/studio/hooks/permission_bridge.py\"",
            "timeout": 600
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.devvenv/bin/python -m pytest studio/tests/test_permission_hook.py -q`
Expected: all PASS.

- [ ] **Step 5: Verify the hook is inert outside a Studio repo**

This guards the claim that installing the plugin is safe everywhere. Run the hook by hand against a directory with no mailbox:

```bash
echo '{"hook_event_name":"PermissionRequest","cwd":"/tmp","tool_name":"Write","tool_input":{"file_path":"/tmp/x","content":"y"}}' \
  | .devvenv/bin/python studio/hooks/permission_bridge.py; echo "exit=$?"
```

Expected: no output at all, `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add hooks/hooks.json studio/tests/test_permission_hook.py
git commit -m "feat(studio): register the permission bridge as a plugin hook"
```

---

## Task 6: The per-repo allowlist scaffold

Independent of Task 1's outcome — this is the half that removes prompts rather than routing them.

**Files:**
- Create: `skills/agentqa-init/scripts/scaffold-permissions.sh`
- Create: `skills/agentqa-init/tests/test_scaffold_permissions.py`
- Modify: `skills/agentqa-init/references/init.md`

**Interfaces:**
- Produces: `scaffold-permissions.sh [--check]`, reading `test_dir` from `<repo>/.agentqa/config.yml`, writing `<repo>/.claude/settings.json`. Follows `scaffold-memory.sh`'s conventions: `AGENTQA_PROJECT_ROOT` override, `--check` mode, non-zero exit on gaps.

- [ ] **Step 1: Write the failing tests**

Create `skills/agentqa-init/tests/test_scaffold_permissions.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.devvenv/bin/python -m pytest skills/agentqa-init/tests/test_scaffold_permissions.py -q`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Write the script**

Create `skills/agentqa-init/scripts/scaffold-permissions.sh`:

```bash
#!/usr/bin/env bash
# Allow AgentQA's own writes without a permission dialog, so a Studio run only
# raises a card for changes outside its working area. Idempotent; merges.
# Usage: scaffold-permissions.sh [--check]   (--check: validate only)
set -euo pipefail

ROOT="${AGENTQA_PROJECT_ROOT:-$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

python3 - "$ROOT" "$CHECK" <<'PY'
import json, re, sys
from pathlib import Path

root, check = Path(sys.argv[1]), sys.argv[2] == "1"

# test_dir is the one repo-specific piece; everything else is fixed.
test_dir = "AutomationTests"
cfg = root / ".agentqa" / "config.yml"
if cfg.is_file():
    m = re.search(r"^test_dir:\s*(\S+)", cfg.read_text(encoding="utf-8"), re.M)
    if m:
        test_dir = m.group(1).strip().strip("\"'")

# Edit(...) and not Write(...): Claude Code's file permission checks match only
# Edit(path) and Read(path) rules. Edit covers every file-editing tool; a
# Write(path) rule is accepted, warned about at startup, and never matched.
wanted = ["Edit(/.agentqa/**)", "Edit(/%s/**)" % test_dir.strip("/")]

path = root / ".claude" / "settings.json"
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print("settings.json is not valid JSON — fix it by hand", file=sys.stderr)
        sys.exit(1)

allow = list(((data.get("permissions") or {}).get("allow")) or [])
missing = [r for r in wanted if r not in allow]

if check:
    if missing:
        print("permission scaffold: missing %s" % ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    print("permission scaffold: OK")
    sys.exit(0)

allow.extend(missing)
data.setdefault("permissions", {})["allow"] = allow
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("permission scaffold: %d rule(s) added" % len(missing))
PY
```

- [ ] **Step 4: Make it executable and run the tests**

```bash
chmod +x skills/agentqa-init/scripts/scaffold-permissions.sh
.devvenv/bin/python -m pytest skills/agentqa-init/tests/test_scaffold_permissions.py -q
```
Expected: all PASS.

- [ ] **Step 5: Document the step in init.md**

In `skills/agentqa-init/references/init.md`, after the memory-scaffold section (around line 87-91), add a section following the same shape as its neighbours:

```markdown
## 5. Scaffold the permission allowlist

AgentQA writes to `.agentqa/` and the test dir on every run. Without an allowlist
each of those writes raises a permission dialog in the terminal — invisible to
anyone driving the run from the Studio dashboard. Add the rules with:

```bash
scripts/scaffold-permissions.sh            # from the host repo root
```

It merges into any existing `.claude/settings.json` and is safe to re-run.
Writes outside those two areas still ask, which is the point: during a Studio
session they become a card in the browser.
```

Renumber the sections that follow it, and add to the validation list near line 139:

```markdown
- `scripts/scaffold-permissions.sh --check` should print `permission scaffold: OK`
```

- [ ] **Step 6: Run the init suite**

Run: `.devvenv/bin/python -m pytest skills/agentqa-init/tests -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add skills/agentqa-init/scripts/scaffold-permissions.sh \
        skills/agentqa-init/tests/test_scaffold_permissions.py \
        skills/agentqa-init/references/init.md
git commit -m "feat(init): scaffold the AgentQA permission allowlist"
```

---

## Task 7: Documentation

**Files:**
- Modify: `docs/agentqa-studio.md`
- Modify: `skills/agentqa-studio/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Add the Permission card to the card table**

In `docs/agentqa-studio.md`, in the checkpoint-card table (around line 73-78), add a row after **System dialog**:

```markdown
| **Permission** | when Claude Code would otherwise raise a permission dialog in the terminal — approve or reject the write, with a note the agent receives |
```

- [ ] **Step 2: Explain the split, near that table**

Add below the table:

```markdown
**Why some writes never ask.** `/agentqa-init init` allowlists `.agentqa/**` and
your `test_dir`, because those are AgentQA's own working area and the step-8
Review card already shows you their diff before anything is kept. Everything else
— app source, or any path outside those two — raises a Permission card. If no
agent is attached to Studio, nothing changes: the prompt appears in the terminal
exactly as before.
```

- [ ] **Step 3: Note the bridge in the connector skill**

In `skills/agentqa-studio/SKILL.md`, add one paragraph at the end of the mailbox section, before `## Prerequisites`. Keep it short — this is the hot-path file and the agent does not act on it, it only needs to not be surprised:

```markdown
Claude Code's own permission dialogs are bridged separately, by a plugin hook
rather than by you: when a write needs approval it becomes a Permission card in
the same conversation. You do nothing to make that happen, and a rejection comes
back to you as an ordinary tool rejection carrying the tester's reason.
```

- [ ] **Step 4: Add the hooks dir to the README tree**

In `README.md`, in the repo-layout block, add after the `studio/` line:

```markdown
hooks/                    # plugin hooks: PermissionRequest -> Studio permission card
```

- [ ] **Step 5: Verify the docs match the code**

```bash
grep -n "Permission" docs/agentqa-studio.md
grep -rn "permission" studio/static/app.js | grep CARD_SUBTYPE
```
Expected: the doc row exists and the label is registered — the two must agree, since the doc names what the tester sees on the card.

- [ ] **Step 6: Full suite and commit**

```bash
.devvenv/bin/python -m pytest studio/tests skills/agentqa-studio/tests skills/agentqa-init/tests -q
git add docs/agentqa-studio.md skills/agentqa-studio/SKILL.md README.md
git commit -m "docs(studio): document the permission bridge"
```

---

## Task 8: Enable it on the real repo and confirm end to end

The only step that proves the feature, rather than its parts.

**Files:**
- Modify: `/Users/anhtuannguyen/Desktop/test-auto-mytv/.claude/settings.json` (via the scaffold script)

- [ ] **Step 1: Scaffold the allowlist there**

```bash
AGENTQA_PROJECT_ROOT=/Users/anhtuannguyen/Desktop/test-auto-mytv \
  bash skills/agentqa-init/scripts/scaffold-permissions.sh
```
Expected: `permission scaffold: 2 rule(s) added`. Confirm `enabledPlugins` survived:
```bash
cat /Users/anhtuannguyen/Desktop/test-auto-mytv/.claude/settings.json
```

- [ ] **Step 2: Run a Studio session and watch for the absence of prompts**

Start `/agentqa-studio` in that repo and give it a small test idea. Writes to
`.agentqa/` and `AutomationTests/` must now proceed with no terminal prompt.

- [ ] **Step 3: Confirm an app-source edit becomes a card**

When the flow reaches the accessibility-identifier step, a **Permission** card must
appear in the browser naming the `.swift` file. Approve it and confirm the edit lands.

- [ ] **Step 4: Confirm rejection carries the reason**

On a second run, reject one with a note. Confirm the agent reports back something
that reflects the note rather than a bare rejection. If Task 1's spike showed
stderr does not reach the model, expect the bare rejection instead and implement
the `studio-read.py --last-reply` fallback the spec describes.

- [ ] **Step 5: Confirm the terminal path is untouched**

Run `/agentqa-write-test` in the same repo with no Studio agent attached. Prompts
for app-source edits must appear in the terminal exactly as before — this is the
guarantee that installing the plugin changes nothing for terminal users.

- [ ] **Step 6: Record the outcome**

If anything differed from the above, write it into the spec's "Decisions locked"
section before closing out the work.
