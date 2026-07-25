# AgentQA Studio — M2 (Agent Bridge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the agent bridge to AgentQA Studio — a versioned file "mailbox" and a `/agentqa-studio` connector skill — so the whole `agentqa-write-test` flow can be driven from the browser, with its three human checkpoints (clarify / build / review) plus step-3 system-view asks rendered as browser cards.

**Architecture:** A brainless daemon and an independent worker communicate only through append-only JSONL files under `.agentqa/studio/`, governed by the **Studio Protocol v1**. The daemon (`studio/protocol.py` + `studio/mailbox.py` + new `server.py` routes) only bridges the browser to those files; the worker (helper scripts under `skills/agentqa-studio/scripts/` driven by the connector skill) reads/writes them directly. Both sides are validated against one canonical fixture, `studio/protocol/v1.json`. The connector is a thin transport adapter over the **unchanged** `agentqa-write-test` flow.

**Tech Stack:** Python 3.9.6 stdlib (`http.server`, `os`, `json`, `uuid`, `datetime`, `subprocess`), vanilla HTML/CSS/JS, pytest.

## Global Constraints

- **No new runtime dependencies.** Stdlib only, both daemon and scripts. (verbatim house rule)
- **Python 3.9.6** — no 3.10+ syntax (no `match`, no `X | Y` unions in annotations; use `Optional[...]`, `Dict[...]`).
- **Stdlib `http.server` only** — no Flask, no npm, no build step.
- **Studio port 7332** (Appium owns 4723).
- **Credential values are never stored or logged** — the agent flow uses the session env like the terminal; the mailbox never carries credential values.
- **Every protocol record carries `v: 1`.** Volatile fields `v`/`id`/`ts`/`type` are stamped by the builder and cannot be overridden by payload.
- **The daemon never writes the outbox and never reads it to act.** It only appends browser messages to the inbox, tails the outbox to the browser, and reads `state.json`.
- **`agentqa-write-test` and `agentqa-init` are NOT modified.** The connector self-manages its gitignore; the redirect is purely "when the flow says *ask the user*, post a question instead."
- **The connector skill is created via the `skill-creator` skill** — not hand-rolled.
- **No commits or pushes without the user's say-so.** Each task ends with a `git commit` *only after the user approves that task's diff*; never push.

**Test venv:** run daemon-side tests with `.devvenv/bin/pytest studio/tests -v` and agent-side tests with `.devvenv/bin/pytest skills/agentqa-studio/tests -v`, both from the repo root.

---

## File Structure

**Daemon side (repo-root `studio/` package):**
- `studio/protocol.py` — Studio Protocol v1: version, type/kind constants, id/ts, record builders (`build_job`, `build_reply`), `validate()`. Pure, no IO.
- `studio/protocol/v1.json` — the canonical golden fixture: one example of every message + the `state.json` shape. Source of truth both sides test against.
- `studio/mailbox.py` — daemon-side IO: append to inbox, read `state.json`, `read_outbox`, `tail_outbox`. Imports `protocol`.
- `studio/server.py` — **modify**: add `/api/studio/{state,job,reply,stream}` routes + `_sse_outbox`.

**Agent side (`skills/agentqa-studio/`):**
- `skills/agentqa-studio/scripts/studio_common.py` — self-contained agent-side half: version, id/ts, `record()`, `append_line`, `post_outbox`, `read_inbox`, `read_state`, `write_state`, `studio_dir`.
- `skills/agentqa-studio/scripts/studio-post.py` — build+post a `progress`/`question`/`result`/`error` record, update state.
- `skills/agentqa-studio/scripts/studio-attach.py` — ensure mailbox dir + `.gitignore`, init state.
- `skills/agentqa-studio/scripts/studio-detach.py` — mark detached/idle.
- `skills/agentqa-studio/scripts/studio-wait.py` — block-poll inbox for the next job or a reply; heartbeat; job cursor; waiting/answered JSON payload.
- `skills/agentqa-studio/SKILL.md` — the connector skill (authored via skill-creator).

**Frontend (modify):** `studio/static/index.html`, `app.js`, `style.css` — add Panel 3.

**Tests:** `studio/tests/test_protocol.py`, `test_mailbox.py`, extend `test_server.py`; `skills/agentqa-studio/tests/test_studio_common.py`, `test_studio_scripts.py`, `test_studio_wait.py`.

---

### Task 1: Studio Protocol v1 — fixture + `studio/protocol.py`

The pure, IO-free definition of the protocol plus the canonical golden fixture.

**Files:**
- Create: `studio/protocol.py`
- Create: `studio/protocol_v1.json` (the canonical golden fixture — a data file beside the module)
- Test: `studio/tests/test_protocol.py`

> **Naming note:** to avoid a module/package name clash, the fixture is
> `studio/protocol_v1.json` (a data file beside the `studio/protocol.py` module),
> not `studio/protocol/v1.json`. The spec's `studio/protocol/v1.json` is realized
> as `studio/protocol_v1.json`.

**Interfaces:**
- Produces:
  - `PROTOCOL_VERSION: int = 1`
  - `INBOX_TYPES`, `OUTBOX_TYPES`, `QUESTION_KINDS`, `QUESTION_SUBTYPES`, `RESULT_STATUSES` — `frozenset`s.
  - `new_id() -> str`, `now_ts() -> str`
  - `record(type_: str, **payload) -> Dict[str, Any]` — stamps `v`/`id`/`ts`/`type` last (payload cannot override them).
  - `build_job(flow_idea: str) -> Dict[str, Any]`
  - `build_reply(reply_to: str, **payload) -> Dict[str, Any]`
  - `validate(rec: Dict[str, Any]) -> Dict[str, Any]` — returns `rec` or raises `ProtocolError` (a `ValueError` subclass).

- [ ] **Step 1: Write the canonical fixture `studio/protocol_v1.json`**

```json
{
  "version": 1,
  "inbox": {
    "job": {"v": 1, "id": "j1", "ts": "2026-07-25T10:00:00Z", "type": "job", "flow_idea": "log in with valid credentials"},
    "reply_form": {"v": 1, "id": "r1", "ts": "2026-07-25T10:01:00Z", "type": "reply", "reply_to": "q1", "answers": {"success": "lands on the home tab", "failure": "inline error under the field", "blockers": "none", "entry": "welcome screen"}},
    "reply_build": {"v": 1, "id": "r2", "ts": "2026-07-25T10:05:00Z", "type": "reply", "reply_to": "q2", "decision": "built"},
    "reply_review": {"v": 1, "id": "r3", "ts": "2026-07-25T10:09:00Z", "type": "reply", "reply_to": "q3", "decision": "approve", "note": null}
  },
  "outbox": {
    "progress": {"v": 1, "id": "p1", "ts": "2026-07-25T10:00:05Z", "type": "progress", "text": "Indexing with CodeGraph…", "stage": "map"},
    "question_clarify": {"v": 1, "id": "q1", "ts": "2026-07-25T10:00:30Z", "type": "question", "kind": "form", "subtype": "clarify", "prompt": "Confirm what this flow should prove", "questions": [{"qid": "success", "label": "What does success look like?", "kind": "text", "default": "lands on the home tab"}, {"qid": "failure", "label": "What does failure look like?", "kind": "text"}, {"qid": "blockers", "label": "Anything that could block the test?", "kind": "text"}, {"qid": "entry", "label": "Which entry point?", "kind": "choice", "options": ["welcome screen", "account tab"]}]},
    "question_ask": {"v": 1, "id": "qa", "ts": "2026-07-25T10:02:00Z", "type": "question", "kind": "form", "subtype": "ask", "prompt": "A location permission prompt appeared.", "questions": [{"qid": "action", "label": "What should the test do?", "kind": "choice", "options": ["Allow", "Deny", "Dismiss"]}]},
    "question_build": {"v": 1, "id": "q2", "ts": "2026-07-25T10:04:00Z", "type": "question", "kind": "confirm", "subtype": "build", "prompt": "Build & install the app onto the booted simulator, then confirm."},
    "question_review": {"v": 1, "id": "q3", "ts": "2026-07-25T10:08:00Z", "type": "question", "kind": "review", "subtype": "review", "prompt": "Review the additions and the test.", "diff": "+ accessibilityIdentifier(\"login_submit_button\")", "test_files": [{"path": "AutomationTests/tests/test_login.py", "content": "def test_login():\n    ...\n"}]},
    "result": {"v": 1, "id": "res1", "ts": "2026-07-25T10:10:00Z", "type": "result", "status": "green", "summary": "login test passing", "test_path": "AutomationTests/tests/test_login.py"},
    "error": {"v": 1, "id": "e1", "ts": "2026-07-25T10:10:00Z", "type": "error", "text": "could not reach the simulator"}
  },
  "state": {"v": 1, "attached": true, "heartbeat_ts": "2026-07-25T10:08:30Z", "status": "waiting", "current_job_id": "j1", "awaiting": "q3", "job_cursor": "j1"}
}
```

- [ ] **Step 2: Write the failing tests**

```python
# studio/tests/test_protocol.py
import json
from pathlib import Path

import pytest

from studio import protocol

FIXTURE = json.loads((Path(protocol.__file__).parent / "protocol_v1.json").read_text())


def test_record_stamps_and_cannot_be_overridden():
    rec = protocol.record("progress", text="hi", type="EVIL", v=99, id="x")
    assert rec["v"] == 1
    assert rec["type"] == "progress"      # payload's type/v/id are ignored
    assert rec["id"] != "x" and rec["id"]
    assert rec["ts"]
    assert rec["text"] == "hi"


def test_build_job_matches_fixture_shape():
    fx = FIXTURE["inbox"]["job"]
    built = protocol.build_job(fx["flow_idea"])
    assert {k: built[k] for k in ("v", "type", "flow_idea")} == \
           {k: fx[k] for k in ("v", "type", "flow_idea")}


def test_build_reply_carries_decision():
    r = protocol.build_reply("q2", decision="built")
    assert r["type"] == "reply" and r["reply_to"] == "q2" and r["decision"] == "built"


@pytest.mark.parametrize("group", ["inbox", "outbox"])
def test_validate_accepts_every_fixture_record(group):
    for rec in FIXTURE[group].values():
        assert protocol.validate(rec) is rec


def test_validate_rejects_bad_records():
    for bad in [
        {"v": 2, "id": "a", "ts": "t", "type": "job", "flow_idea": "x"},   # version
        {"v": 1, "id": "a", "ts": "t", "type": "job"},                     # no flow_idea
        {"v": 1, "id": "a", "ts": "t", "type": "reply"},                   # no reply_to
        {"v": 1, "id": "a", "ts": "t", "type": "nope"},                    # bad type
        {"v": 1, "id": "a", "ts": "t", "type": "question", "kind": "x", "subtype": "clarify"},
        {"v": 1, "id": "a", "ts": "t", "type": "result", "status": "x"},
    ]:
        with pytest.raises(protocol.ProtocolError):
            protocol.validate(bad)
```

- [ ] **Step 3: Run to verify they fail**

Run: `.devvenv/bin/pytest studio/tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'studio.protocol'`

- [ ] **Step 4: Write `studio/protocol.py`**

```python
"""Studio Protocol v1 — message shapes, builders, and validation. No IO.

The canonical definition of every message is studio/protocol_v1.json (the golden
fixture both the daemon and the connector test against). This module is the
daemon-side executable half: it stamps v/id/ts, builds the records the daemon
produces (job, reply), and validates any record before it is appended or streamed.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

PROTOCOL_VERSION = 1

INBOX_TYPES = frozenset({"job", "reply"})
OUTBOX_TYPES = frozenset({"progress", "question", "result", "error"})
QUESTION_KINDS = frozenset({"form", "confirm", "review"})
QUESTION_SUBTYPES = frozenset({"clarify", "ask", "build", "review"})
RESULT_STATUSES = frozenset({"green", "abandoned"})


class ProtocolError(ValueError):
    """A record that does not conform to Studio Protocol v1."""


def new_id() -> str:
    return uuid.uuid4().hex


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(type_: str, **payload: Any) -> Dict[str, Any]:
    """Stamp a record. v/id/ts/type are set LAST so payload can't override them."""
    rec = dict(payload)
    rec["v"] = PROTOCOL_VERSION
    rec["id"] = new_id()
    rec["ts"] = now_ts()
    rec["type"] = type_
    return rec


def build_job(flow_idea: str) -> Dict[str, Any]:
    return record("job", flow_idea=flow_idea)


def build_reply(reply_to: str, **payload: Any) -> Dict[str, Any]:
    return record("reply", reply_to=reply_to, **payload)


def validate(rec: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(rec, dict):
        raise ProtocolError("record must be an object")
    if rec.get("v") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version: %r" % rec.get("v"))
    for key in ("id", "ts", "type"):
        if not rec.get(key):
            raise ProtocolError("record missing %r" % key)
    t = rec["type"]
    if t not in INBOX_TYPES | OUTBOX_TYPES:
        raise ProtocolError("unknown type: %r" % t)
    if t == "job" and not rec.get("flow_idea"):
        raise ProtocolError("job missing flow_idea")
    if t == "reply" and not rec.get("reply_to"):
        raise ProtocolError("reply missing reply_to")
    if t == "question":
        if rec.get("kind") not in QUESTION_KINDS:
            raise ProtocolError("question kind invalid: %r" % rec.get("kind"))
        if rec.get("subtype") not in QUESTION_SUBTYPES:
            raise ProtocolError("question subtype invalid: %r" % rec.get("subtype"))
    if t == "result" and rec.get("status") not in RESULT_STATUSES:
        raise ProtocolError("result status invalid: %r" % rec.get("status"))
    return rec
```

- [ ] **Step 5: Run to verify they pass**

Run: `.devvenv/bin/pytest studio/tests/test_protocol.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit (only after the user approves this task's diff)**

```bash
git add studio/protocol.py studio/protocol_v1.json studio/tests/test_protocol.py
git commit -m "feat(studio): Studio Protocol v1 — golden fixture + builders/validation"
```

---

### Task 2: Mailbox IO — `studio/mailbox.py`

Daemon-side IO over the mailbox files. Appends browser messages to the inbox,
reads `state.json`, and tails the outbox for SSE.

**Files:**
- Create: `studio/mailbox.py`
- Test: `studio/tests/test_mailbox.py`

**Interfaces:**
- Consumes: `studio.protocol` (`validate`, `PROTOCOL_VERSION`).
- Produces:
  - `studio_dir(repo_root: Path) -> Path` → `<repo>/.agentqa/studio`.
  - `append_inbox(repo_root: Path, rec: Dict) -> Dict` — validates then appends to `inbox.jsonl`.
  - `read_outbox(repo_root: Path) -> List[Dict]` — all outbox records (skips a partial trailing line).
  - `read_state(repo_root: Path) -> Dict` — `state.json` or a default idle/detached dict.
  - `tail_outbox(repo_root: Path, poll: float=0.5) -> Iterator[Optional[Dict]]` — yields each outbox record oldest-first, then new ones as they arrive; yields `None` on an idle tick (SSE keepalive / disconnect probe). Never returns on its own.

- [ ] **Step 1: Write the failing tests**

```python
# studio/tests/test_mailbox.py
from pathlib import Path

import pytest

from studio import mailbox, protocol


def test_append_inbox_validates_and_writes(tmp_path):
    rec = mailbox.append_inbox(tmp_path, protocol.build_job("log in"))
    line = (mailbox.studio_dir(tmp_path) / "inbox.jsonl").read_text().strip()
    assert '"type": "job"' in line
    assert rec["flow_idea"] == "log in"


def test_append_inbox_rejects_bad_record(tmp_path):
    with pytest.raises(protocol.ProtocolError):
        mailbox.append_inbox(tmp_path, {"v": 1, "id": "x", "ts": "t", "type": "job"})


def test_read_state_default_when_absent(tmp_path):
    st = mailbox.read_state(tmp_path)
    assert st["attached"] is False and st["status"] == "idle"


def test_read_state_reads_file(tmp_path):
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "state.json").write_text('{"v":1,"attached":true,"status":"running"}')
    assert mailbox.read_state(tmp_path)["status"] == "running"


def test_read_outbox_skips_partial_trailing_line(tmp_path):
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "outbox.jsonl").write_text('{"a": 1}\n{"b": 2}\n{"partial"')
    assert mailbox.read_outbox(tmp_path) == [{"a": 1}, {"b": 2}]


def test_tail_outbox_yields_records_then_keepalive(tmp_path):
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "outbox.jsonl").write_text('{"a": 1}\n{"b": 2}\n')
    it = mailbox.tail_outbox(tmp_path, poll=0.01)
    assert next(it) == {"a": 1}
    assert next(it) == {"b": 2}
    assert next(it) is None          # nothing new → keepalive tick
```

- [ ] **Step 2: Run to verify they fail**

Run: `.devvenv/bin/pytest studio/tests/test_mailbox.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'studio.mailbox'`

- [ ] **Step 3: Write `studio/mailbox.py`**

```python
"""Studio mailbox IO (daemon side): append inbox, read state, tail outbox.

Half A only ever bridges the browser to these files — it appends the browser's
messages to the inbox, tails the outbox to the browser, and reads state.json. It
never writes the outbox and never reads the outbox to act. The agent side owns the
outbox and state and touches these files directly, not through this module.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from studio import protocol


def studio_dir(repo_root: Path) -> Path:
    return Path(repo_root) / ".agentqa" / "studio"


def _append_line(path: Path, rec: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    # O_APPEND makes each write atomic against other appenders; a full-line write
    # means a reader never sees half a record.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def append_inbox(repo_root: Path, rec: Dict[str, Any]) -> Dict[str, Any]:
    protocol.validate(rec)
    _append_line(studio_dir(repo_root) / "inbox.jsonl", rec)
    return rec


def read_outbox(repo_root: Path) -> List[Dict[str, Any]]:
    path = studio_dir(repo_root) / "outbox.jsonl"
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    # Only consume newline-terminated (complete) lines; a partial trailing line
    # with no "\n" yet is left for a later read.
    complete = text.split("\n")[: text.count("\n")]
    for raw in complete:
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except ValueError:
                pass
    return out


def read_state(repo_root: Path) -> Dict[str, Any]:
    path = studio_dir(repo_root) / "state.json"
    if not path.is_file():
        return {"v": protocol.PROTOCOL_VERSION, "attached": False, "status": "idle",
                "current_job_id": None, "awaiting": None, "heartbeat_ts": None,
                "job_cursor": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"v": protocol.PROTOCOL_VERSION, "attached": False, "status": "idle"}


def tail_outbox(repo_root: Path, poll: float = 0.5) -> Iterator[Optional[Dict[str, Any]]]:
    """Yield outbox records oldest-first then follow appends; None on idle ticks.

    The SSE handler turns a record into a `data:` event and None into a `: ping`
    comment — the comment doubles as a disconnect probe so a closed browser stops
    the stream. The caller stops iterating on client disconnect.
    """
    path = studio_dir(repo_root) / "outbox.jsonl"
    seen = 0
    while True:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        complete = text.count("\n")
        if complete > seen:
            rows = text.split("\n")
            for raw in rows[seen:complete]:
                raw = raw.strip()
                if raw:
                    try:
                        yield json.loads(raw)
                    except ValueError:
                        pass
            seen = complete
        else:
            yield None
            time.sleep(poll)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.devvenv/bin/pytest studio/tests/test_mailbox.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit (only after the user approves this task's diff)**

```bash
git add studio/mailbox.py studio/tests/test_mailbox.py
git commit -m "feat(studio): mailbox IO — inbox append, state read, outbox tail"
```

---

### Task 3: Server endpoints + SSE outbox tail (`studio/server.py`)

Wire the mailbox behind four routes. The daemon stays brainless: `job`/`reply`
only append to the inbox, `state` reads `state.json`, `stream` tails the outbox.

**Files:**
- Modify: `studio/server.py` (imports; `do_GET` at line 76 region; `do_POST` at line 89 region; add `_sse_outbox`)
- Test: `studio/tests/test_server.py` (append tests)

**Interfaces:**
- Consumes: `studio.mailbox`, `studio.protocol`.
- Produces routes:
  - `GET  /api/studio/state` → `read_state(repo_root)`.
  - `POST /api/studio/job {flow_idea}` → 409 if `state.status` in `{running, waiting}`; else append a `job`; returns `{ok, id}`.
  - `POST /api/studio/reply {reply_to, …}` → append a `reply`; returns `{ok, id}`.
  - `GET  /api/studio/stream` → SSE tailing the outbox.

- [ ] **Step 1: Add the import (top of `studio/server.py`)**

Change line 11–12:

```python
from studio import config as cfgmod
from studio import mailbox, memory_view, protocol, rig, runner
```

- [ ] **Step 2: Add GET routes** — in `do_GET`, immediately before `if u.path == "/api/run/stream":` (line 76):

```python
                if u.path == "/api/studio/state":
                    return self._json(mailbox.read_state(repo_root))
                if u.path == "/api/studio/stream":
                    return self._sse_outbox()
```

- [ ] **Step 3: Add POST routes** — in `do_POST`, immediately before `return self._json({"error": "not found"}, 404)` (line 103):

```python
                if u.path == "/api/studio/job":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict) or not payload.get("flow_idea"):
                        return self._json({"error": "flow_idea required"}, 400)
                    st = mailbox.read_state(repo_root)
                    if st.get("status") in ("running", "waiting"):
                        return self._json({"error": "a job is already running"}, 409)
                    rec = mailbox.append_inbox(repo_root, protocol.build_job(payload["flow_idea"]))
                    return self._json({"ok": True, "id": rec["id"]})
                if u.path == "/api/studio/reply":
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict) or not payload.get("reply_to"):
                        return self._json({"error": "reply_to required"}, 400)
                    reply_to = payload.pop("reply_to")
                    rec = mailbox.append_inbox(repo_root, protocol.build_reply(reply_to, **payload))
                    return self._json({"ok": True, "id": rec["id"]})
```

- [ ] **Step 4: Add the SSE method** — inside `Handler`, after `_sse` (after line 124):

```python
        def _sse_outbox(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for rec in mailbox.tail_outbox(repo_root):
                    if rec is None:
                        self.wfile.write(b": ping\n\n")
                    else:
                        self.wfile.write(("data: %s\n\n" % json.dumps(rec)).encode())
                    self.wfile.flush()
            except Exception:
                return
```

- [ ] **Step 5: Append failing tests to `studio/tests/test_server.py`**

```python
def _post(base, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def _studio_dir(tmp):
    from studio import mailbox
    return mailbox.studio_dir(tmp)


def test_studio_state_default(live_server):
    status, body = _get(live_server, "/api/studio/state")
    assert status == 200
    assert json.loads(body)["attached"] is False


def test_studio_job_appends_to_inbox(live_server, tmp_path):
    status, body = _post(live_server, "/api/studio/job", {"flow_idea": "log in"})
    assert status == 200 and body["ok"] is True
    inbox = (_studio_dir(tmp_path) / "inbox.jsonl").read_text()
    assert '"type": "job"' in inbox and "log in" in inbox


def test_studio_job_409_when_running(live_server, tmp_path):
    d = _studio_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text('{"v":1,"attached":true,"status":"running"}')
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(live_server, "/api/studio/job", {"flow_idea": "x"})
    assert exc.value.code == 409


def test_studio_reply_appends(live_server, tmp_path):
    status, body = _post(
        live_server, "/api/studio/reply", {"reply_to": "q1", "decision": "built"})
    assert status == 200
    inbox = (_studio_dir(tmp_path) / "inbox.jsonl").read_text()
    assert '"type": "reply"' in inbox and '"reply_to": "q1"' in inbox


def test_studio_stream_replays_outbox(live_server, tmp_path):
    d = _studio_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "outbox.jsonl").write_text('{"type":"progress","text":"hi"}\n')
    with urllib.request.urlopen(live_server + "/api/studio/stream", timeout=5) as r:
        for _ in range(20):
            line = r.readline().decode()
            if line.startswith("data:"):
                assert '"text":"hi"' in line or '"text": "hi"' in line
                return
    assert False, "no data event received"
```

The existing `live_server` fixture uses `tmp_path` as the repo root, so `tmp_path`
is the same directory the server reads — the `tmp_path` argument here refers to
the same fixture-scoped temp dir.

- [ ] **Step 6: Run to verify they fail, then pass after Steps 1–4**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v`
Expected after edits: PASS (M1 tests + the five new studio tests)

- [ ] **Step 7: Commit (only after the user approves this task's diff)**

```bash
git add studio/server.py studio/tests/test_server.py
git commit -m "feat(studio): mailbox endpoints — state, job (409 guard), reply, SSE stream"
```

---

### Task 4: Agent-side toolkit — `studio_common.py` + post / attach / detach

The self-contained agent half of the protocol (no dependency on the `studio`
package or the daemon) plus the three "producer" scripts. `studio-wait.py` (the
subtle consumer) is Task 5.

**Files:**
- Create: `skills/agentqa-studio/scripts/studio_common.py`
- Create: `skills/agentqa-studio/scripts/studio-post.py`
- Create: `skills/agentqa-studio/scripts/studio-attach.py`
- Create: `skills/agentqa-studio/scripts/studio-detach.py`
- Create: `skills/agentqa-studio/tests/test_studio_common.py`
- Create: `skills/agentqa-studio/tests/test_studio_scripts.py`

**Interfaces:**
- `studio_common`: `PROTOCOL_VERSION`, `studio_dir(repo)`, `new_id()`, `now_ts()`, `record(type_, **payload)` (v/id/ts/type stamped last), `append_line(path, rec)`, `post_outbox(repo, rec)`, `read_inbox(repo) -> list`, `read_state(repo) -> dict`, `write_state(repo, **updates) -> dict` (merges, stamps `v`, bumps `heartbeat_ts`).
- Scripts expose `main(argv=None) -> int`; `sys.exit(main())` at import guard.

- [ ] **Step 1: Write the failing tests**

```python
# skills/agentqa-studio/tests/test_studio_common.py
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import studio_common as sc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((REPO_ROOT / "studio" / "protocol_v1.json").read_text())


def test_record_matches_fixture_progress():
    fx = FIXTURE["outbox"]["progress"]
    rec = sc.record("progress", text=fx["text"], stage=fx["stage"])
    assert {k: rec[k] for k in ("v", "type", "text", "stage")} == \
           {k: fx[k] for k in ("v", "type", "text", "stage")}


def test_record_cannot_be_overridden():
    rec = sc.record("progress", type="EVIL", v=9)
    assert rec["type"] == "progress" and rec["v"] == 1


def test_post_outbox_and_read_state_roundtrip(tmp_path):
    sc.post_outbox(tmp_path, sc.record("progress", text="hi"))
    text = (sc.studio_dir(tmp_path) / "outbox.jsonl").read_text().strip()
    assert json.loads(text)["text"] == "hi"


def test_write_state_bumps_heartbeat_and_merges(tmp_path):
    sc.write_state(tmp_path, status="running", current_job_id="j1")
    st = sc.read_state(tmp_path)
    assert st["status"] == "running" and st["current_job_id"] == "j1"
    assert st["v"] == 1 and st["heartbeat_ts"]
    sc.write_state(tmp_path, attached=False)     # explicit False must stick
    assert sc.read_state(tmp_path)["attached"] is False


def test_read_inbox_parses_lines(tmp_path):
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", {"type": "job", "id": "j1"})
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", {"type": "reply", "id": "r1"})
    assert [r["type"] for r in sc.read_inbox(tmp_path)] == ["job", "reply"]
```

```python
# skills/agentqa-studio/tests/test_studio_scripts.py
import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import studio_common as sc  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


post = _load("studio-post.py")
attach = _load("studio-attach.py")
detach = _load("studio-detach.py")


def test_attach_creates_gitignore_and_state(tmp_path):
    assert attach.main([str(tmp_path)]) == 0
    gi = sc.studio_dir(tmp_path) / ".gitignore"
    assert gi.read_text().strip() == "*"
    st = sc.read_state(tmp_path)
    assert st["attached"] is True and st["status"] == "idle"


def test_post_question_sets_waiting(tmp_path, capsys):
    rc = post.main([str(tmp_path), "question", "--kind", "confirm",
                    "--subtype", "build", "--prompt", "build it"])
    assert rc == 0
    qid = capsys.readouterr().out.strip()
    st = sc.read_state(tmp_path)
    assert st["status"] == "waiting" and st["awaiting"] == qid
    rec = json.loads((sc.studio_dir(tmp_path) / "outbox.jsonl").read_text().strip())
    assert rec["type"] == "question" and rec["kind"] == "confirm"


def test_post_result_sets_idle(tmp_path):
    post.main([str(tmp_path), "result", "--status", "green", "--summary", "done"])
    assert sc.read_state(tmp_path)["status"] == "idle"


def test_post_progress_with_stage(tmp_path):
    post.main([str(tmp_path), "progress", "--text", "mapping", "--stage", "map"])
    rec = json.loads((sc.studio_dir(tmp_path) / "outbox.jsonl").read_text().strip())
    assert rec["stage"] == "map" and rec["text"] == "mapping"


def test_detach_marks_detached(tmp_path):
    attach.main([str(tmp_path)])
    detach.main([str(tmp_path)])
    assert sc.read_state(tmp_path)["attached"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `.devvenv/bin/pytest skills/agentqa-studio/tests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'studio_common'`

- [ ] **Step 3: Write `studio_common.py`**

```python
"""Studio Protocol v1 — agent-side half. Stdlib only, self-contained.

Mirrors the daemon-side studio/protocol.py + studio/mailbox.py, but lives with the
connector so the worker never depends on the daemon or the studio package. Both
sides are validated against the one canonical fixture, studio/protocol_v1.json.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL_VERSION = 1


def studio_dir(repo_root):
    return Path(repo_root) / ".agentqa" / "studio"


def new_id():
    return uuid.uuid4().hex


def now_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(type_, **payload):
    rec = dict(payload)
    rec["v"] = PROTOCOL_VERSION
    rec["id"] = new_id()
    rec["ts"] = now_ts()
    rec["type"] = type_
    return rec


def append_line(path, rec):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def post_outbox(repo_root, rec):
    append_line(studio_dir(repo_root) / "outbox.jsonl", rec)
    return rec


def read_inbox(repo_root):
    path = studio_dir(repo_root) / "inbox.jsonl"
    if not path.is_file():
        return []
    out = []
    text = path.read_text(encoding="utf-8")
    for raw in text.split("\n")[: text.count("\n")]:
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except ValueError:
                pass
    return out


def read_state(repo_root):
    path = studio_dir(repo_root) / "state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def write_state(repo_root, **updates):
    """Merge updates into state.json; always stamp v and a fresh heartbeat."""
    state = read_state(repo_root)
    state.update(updates)
    state["v"] = PROTOCOL_VERSION
    state.setdefault("attached", True)
    state["heartbeat_ts"] = now_ts()
    d = studio_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state
```

- [ ] **Step 4: Write `studio-post.py`**

```python
#!/usr/bin/env python3
"""Post a Studio Protocol record to the outbox (agent -> browser), update state.

  studio-post.py <repo> progress --text "..." [--stage map]
  studio-post.py <repo> question --kind form   --subtype clarify --prompt "..." --questions '<json array>'
  studio-post.py <repo> question --kind confirm --subtype build  --prompt "..."
  studio-post.py <repo> question --kind review --subtype review  --prompt "..." --diff "<text>" --test-files '<json array>'
  studio-post.py <repo> result   --status green --summary "..." [--test-path ...]
  studio-post.py <repo> error    --text "..."

Prints the record id. A `question` flips state to waiting/awaiting:<id>; a
`result` flips state back to idle; anything else just bumps the heartbeat.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-post.py")
    ap.add_argument("repo")
    sub = ap.add_subparsers(dest="type", required=True)

    p = sub.add_parser("progress")
    p.add_argument("--text", required=True)
    p.add_argument("--stage", default=None)

    q = sub.add_parser("question")
    q.add_argument("--kind", required=True, choices=["form", "confirm", "review"])
    q.add_argument("--subtype", required=True,
                   choices=["clarify", "ask", "build", "review"])
    q.add_argument("--prompt", required=True)
    q.add_argument("--questions", default=None, help="JSON array for form questions")
    q.add_argument("--diff", default=None)
    q.add_argument("--test-files", default=None, help="JSON array of {path,content}")

    r = sub.add_parser("result")
    r.add_argument("--status", required=True, choices=["green", "abandoned"])
    r.add_argument("--summary", default="")
    r.add_argument("--test-path", default=None)

    e = sub.add_parser("error")
    e.add_argument("--text", required=True)

    args = ap.parse_args(argv)
    repo = Path(args.repo)

    if args.type == "progress":
        payload = {"text": args.text}
        if args.stage:
            payload["stage"] = args.stage
        rec = sc.record("progress", **payload)
    elif args.type == "question":
        payload = {"kind": args.kind, "subtype": args.subtype, "prompt": args.prompt}
        if args.questions:
            payload["questions"] = json.loads(args.questions)
        if args.diff is not None:
            payload["diff"] = args.diff
        if args.test_files:
            payload["test_files"] = json.loads(args.test_files)
        rec = sc.record("question", **payload)
    elif args.type == "result":
        payload = {"status": args.status, "summary": args.summary}
        if args.test_path:
            payload["test_path"] = args.test_path
        rec = sc.record("result", **payload)
    else:  # error
        rec = sc.record("error", text=args.text)

    sc.post_outbox(repo, rec)
    if args.type == "question":
        sc.write_state(repo, status="waiting", awaiting=rec["id"])
    elif args.type == "result":
        sc.write_state(repo, status="idle", awaiting=None)
    else:
        sc.write_state(repo)  # heartbeat bump
    print(rec["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `studio-attach.py`**

```python
#!/usr/bin/env python3
"""Attach the connector: ensure the mailbox dir + gitignore, init state.json."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def ensure_gitignore(repo):
    d = sc.studio_dir(repo)
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text("*\n", encoding="utf-8")   # ignore the whole transient mailbox


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-attach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    ensure_gitignore(repo)
    sc.write_state(repo, attached=True, status="idle",
                   current_job_id=None, awaiting=None)
    print("attached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Write `studio-detach.py`**

```python
#!/usr/bin/env python3
"""Detach the connector: mark state detached/idle."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-detach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    sc.write_state(Path(args.repo), attached=False, status="idle", awaiting=None)
    print("detached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Make scripts executable and run the tests**

```bash
chmod +x skills/agentqa-studio/scripts/studio-post.py \
         skills/agentqa-studio/scripts/studio-attach.py \
         skills/agentqa-studio/scripts/studio-detach.py
.devvenv/bin/pytest skills/agentqa-studio/tests -v
```
Expected: PASS (all)

- [ ] **Step 8: Commit (only after the user approves this task's diff)**

```bash
git add skills/agentqa-studio/scripts/studio_common.py \
        skills/agentqa-studio/scripts/studio-post.py \
        skills/agentqa-studio/scripts/studio-attach.py \
        skills/agentqa-studio/scripts/studio-detach.py \
        skills/agentqa-studio/tests/test_studio_common.py \
        skills/agentqa-studio/tests/test_studio_scripts.py
git commit -m "feat(studio): agent-side toolkit — studio_common + post/attach/detach"
```

---

### Task 5: The blocking wait — `studio-wait.py`

Block-poll the inbox for the next unprocessed `job` or the `reply` to a specific
question. Refresh the heartbeat each tick; signal waiting/answered **in the JSON
payload** (nonzero exit reserved for real failure). A job advances `job_cursor`.

**Files:**
- Create: `skills/agentqa-studio/scripts/studio-wait.py`
- Create: `skills/agentqa-studio/tests/test_studio_wait.py`

**Interfaces:**
- Consumes: `studio_common` (`read_inbox`, `read_state`, `write_state`).
- CLI: `studio-wait.py <repo> (--job | --reply-to <qid>) [--timeout S] [--poll S]`.
- Stdout is exactly one JSON object: `{"status":"answered","record":{...}}` or `{"status":"waiting"}`. Exit `0` for both.
- On an answered `--job`, sets state `status=running, current_job_id=<id>, job_cursor=<id>`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/agentqa-studio/tests/test_studio_wait.py
import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import studio_common as sc  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wait = _load("studio-wait.py")


def _out(capsys):
    return json.loads(capsys.readouterr().out.strip())


def test_wait_job_returns_first_and_sets_running(tmp_path, capsys):
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", sc.record("job", flow_idea="a"))
    rc = wait.main([str(tmp_path), "--job", "--timeout", "0", "--poll", "0"])
    assert rc == 0
    out = _out(capsys)
    assert out["status"] == "answered" and out["record"]["flow_idea"] == "a"
    st = sc.read_state(tmp_path)
    assert st["status"] == "running" and st["job_cursor"] == out["record"]["id"]


def test_wait_job_respects_cursor(tmp_path, capsys):
    a = sc.record("job", flow_idea="a")
    b = sc.record("job", flow_idea="b")
    for r in (a, b):
        sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", r)
    sc.write_state(tmp_path, job_cursor=a["id"])   # a already processed
    wait.main([str(tmp_path), "--job", "--timeout", "0", "--poll", "0"])
    assert _out(capsys)["record"]["flow_idea"] == "b"


def test_wait_reply_matches_qid(tmp_path, capsys):
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl",
                   sc.record("reply", reply_to="q9", decision="built"))
    wait.main([str(tmp_path), "--reply-to", "q9", "--timeout", "0", "--poll", "0"])
    out = _out(capsys)
    assert out["status"] == "answered" and out["record"]["decision"] == "built"


def test_wait_times_out_to_waiting(tmp_path, capsys):
    rc = wait.main([str(tmp_path), "--reply-to", "nope", "--timeout", "0", "--poll", "0"])
    assert rc == 0
    assert _out(capsys)["status"] == "waiting"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.devvenv/bin/pytest skills/agentqa-studio/tests/test_studio_wait.py -v`
Expected: FAIL — module `studio-wait.py` not found

- [ ] **Step 3: Write `studio-wait.py`**

```python
#!/usr/bin/env python3
"""Block-poll the inbox for the next job or a reply, keeping the heartbeat warm.

  studio-wait.py <repo> --job                 # next unprocessed job (respects job_cursor)
  studio-wait.py <repo> --reply-to <qid>      # the reply to a question

Prints exactly one JSON object:
  {"status":"answered","record":{...}}    the awaited job/reply arrived
  {"status":"waiting"}                     timed out under the tool cap — the caller
                                           simply runs it again to re-block

Exit is 0 for both (waiting is not an error). A nonzero exit means the script
itself failed, matching the house convention (0 = ok, nonzero = failure).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc

DEFAULT_TIMEOUT = 480.0   # ~8 min, safely under a 600s tool cap
DEFAULT_POLL = 1.0


def _find_job(repo):
    cursor = sc.read_state(repo).get("job_cursor")
    passed = cursor is None
    for rec in sc.read_inbox(repo):
        if rec.get("type") != "job":
            continue
        if passed:
            return rec
        if rec.get("id") == cursor:
            passed = True
    return None


def _find_reply(repo, qid):
    for rec in sc.read_inbox(repo):
        if rec.get("type") == "reply" and rec.get("reply_to") == qid:
            return rec
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-wait.py")
    ap.add_argument("repo")
    ap.add_argument("--job", action="store_true")
    ap.add_argument("--reply-to", dest="reply_to", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--poll", type=float, default=DEFAULT_POLL)
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    if not args.job and not args.reply_to:
        ap.error("one of --job or --reply-to is required")

    deadline = time.time() + args.timeout
    while True:
        rec = _find_job(repo) if args.job else _find_reply(repo, args.reply_to)
        if rec is not None:
            if args.job:
                sc.write_state(repo, status="running",
                               current_job_id=rec["id"], job_cursor=rec["id"])
            print(json.dumps({"status": "answered", "record": rec}))
            return 0
        if time.time() >= deadline:
            print(json.dumps({"status": "waiting"}))
            return 0
        sc.write_state(repo)          # heartbeat bump while we wait
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make executable and run the tests**

```bash
chmod +x skills/agentqa-studio/scripts/studio-wait.py
.devvenv/bin/pytest skills/agentqa-studio/tests -v
```
Expected: PASS (all agent-side tests)

- [ ] **Step 5: Commit (only after the user approves this task's diff)**

```bash
git add skills/agentqa-studio/scripts/studio-wait.py \
        skills/agentqa-studio/tests/test_studio_wait.py
git commit -m "feat(studio): studio-wait — blocking inbox poll with cursor + heartbeat"
```

---

### Task 6: Panel 3 — Agent conversation UI

Add the fourth panel: attach indicator, job starter, a `stage` stepper, and the
SSE-driven conversation log with the four card widgets. Vanilla JS, no build.

**Files:**
- Modify: `studio/static/index.html` (add the `agent-panel` section)
- Modify: `studio/static/app.js` (append the Panel 3 module)
- Modify: `studio/static/style.css` (append Panel 3 styles)
- Test: `studio/tests/test_server.py` (extend the asset test)

- [ ] **Step 1: Add a failing asset assertion** — replace the existing
`test_static_assets_served` body's loop list so it also requires the new needles:

```python
def test_static_assets_served(live_server):
    for asset, needle in [
        ("/static/app.js", "connectStream"),
        ("/static/style.css", ".stepper"),
    ]:
        status, body = _get(live_server, asset)
        assert status == 200, asset
        assert needle in body, asset
```

- [ ] **Step 2: Run to verify it fails**

Run: `.devvenv/bin/pytest studio/tests/test_server.py::test_static_assets_served -v`
Expected: FAIL (needles absent)

- [ ] **Step 3: Add the Panel 3 section to `index.html`** — insert before
`</main>` (before line 29):

```html
  <section id="agent-panel">
    <h2>Agent</h2>
    <div id="agent-status" class="muted">checking for agent…</div>
    <div class="job-starter">
      <input id="job-idea" type="text" placeholder="Write a test for…" autocomplete="off">
      <button id="job-start">Start</button>
    </div>
    <div id="stepper" class="stepper"></div>
    <div id="agent-log" class="agent-log"></div>
  </section>
```

- [ ] **Step 4: Append the Panel 3 module to `app.js`**

```javascript

// ---- Panel 3: Agent conversation ---------------------------------------
const STAGES = ["map", "clarify", "explore", "identifiers", "build",
                "verify", "write", "green", "review", "capture"];

function renderStepper(current) {
  const box = document.getElementById("stepper");
  const seq = STAGES.includes(current) ? STAGES : STAGES.concat([current]);
  const idx = seq.indexOf(current);
  box.innerHTML = "";
  seq.forEach((s, i) => {
    const cls = i < idx ? "done" : (i === idx ? "active" : "");
    box.appendChild(el(`<span class="step ${cls}">${esc(s)}</span>`));
  });
}

function logAppend(node) {
  const log = document.getElementById("agent-log");
  log.appendChild(node);
  while (log.children.length > 500) log.removeChild(log.firstElementChild);
  log.scrollTop = log.scrollHeight;
}

function appendProgress(rec) {
  logAppend(el(`<div class="msg">${esc(rec.text)}</div>`));
  if (rec.stage) renderStepper(rec.stage);
}

function appendResult(rec) {
  const cls = rec.status === "green" ? "ok" : "bad";
  const path = rec.test_path ? ` — ${esc(rec.test_path)}` : "";
  logAppend(el(`<div class="msg card"><strong class="dot ${cls}">${esc(rec.status)}</strong> ${esc(rec.summary || "")}${path}</div>`));
}

function appendError(rec) {
  logAppend(el(`<div class="msg card"><strong class="dot bad">error</strong> ${esc(rec.text)}</div>`));
}

async function sendReply(payload) {
  await fetchJSON("/api/studio/reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function lockCard(card, summary) {
  card.querySelectorAll("input,button,textarea").forEach((n) => { n.disabled = true; });
  card.appendChild(el(`<div class="muted locked">↳ ${esc(summary)}</div>`));
}

function renderForm(rec, card) {
  const fields = {};
  (rec.questions || []).forEach((q) => {
    const wrap = el(`<div class="field"><label>${esc(q.label)}</label></div>`);
    if (q.kind === "choice") {
      const choices = el(`<div class="choices"></div>`);
      (q.options || []).forEach((opt) => {
        choices.appendChild(el(
          `<label class="opt"><input type="radio" name="${esc(rec.id + q.qid)}" value="${esc(opt)}"> ${esc(opt)}</label>`));
      });
      wrap.appendChild(choices);
    } else {
      wrap.appendChild(el(`<input type="text" value="${esc(q.default || "")}">`));
    }
    card.appendChild(wrap);
    fields[q.qid] = { q, wrap };
  });
  const submit = el(`<button>Submit</button>`);
  submit.onclick = async () => {
    const answers = {};
    for (const [qid, f] of Object.entries(fields)) {
      if (f.q.kind === "choice") {
        const checked = f.wrap.querySelector("input:checked");
        answers[qid] = checked ? checked.value : "";
      } else {
        answers[qid] = f.wrap.querySelector("input").value;
      }
    }
    await sendReply({ reply_to: rec.id, answers });
    lockCard(card, "answered");
  };
  card.appendChild(submit);
}

function renderConfirm(rec, card) {
  const btn = el(`<button>I've built &amp; installed</button>`);
  btn.onclick = async () => {
    await sendReply({ reply_to: rec.id, decision: "built" });
    lockCard(card, "built");
  };
  card.appendChild(btn);
}

function renderReview(rec, card) {
  card.appendChild(el(`<pre class="diffbox">${esc(rec.diff || "")}</pre>`));
  (rec.test_files || []).forEach((f) => {
    card.appendChild(el(`<div class="muted">${esc(f.path)}</div>`));
    card.appendChild(el(`<pre class="diffbox">${esc(f.content)}</pre>`));
  });
  const note = el(`<textarea placeholder="reason (if rejecting)"></textarea>`);
  note.style.display = "none";
  const approve = el(`<button>Approve</button>`);
  const reject = el(`<button>Reject</button>`);
  approve.onclick = async () => {
    await sendReply({ reply_to: rec.id, decision: "approve" });
    lockCard(card, "approved");
  };
  reject.onclick = async () => {
    if (note.style.display === "none") { note.style.display = "block"; return; }
    await sendReply({ reply_to: rec.id, decision: "reject", note: note.value });
    lockCard(card, "rejected");
  };
  const actions = el(`<div class="card-actions"></div>`);
  actions.appendChild(approve);
  actions.appendChild(reject);
  card.appendChild(note);
  card.appendChild(actions);
}

function renderCard(rec) {
  const card = el(`<div class="msg card"></div>`);
  card.appendChild(el(`<div class="prompt">${esc(rec.prompt || "")}</div>`));
  if (rec.kind === "form") renderForm(rec, card);
  else if (rec.kind === "confirm") renderConfirm(rec, card);
  else if (rec.kind === "review") renderReview(rec, card);
  logAppend(card);
}

function dispatch(rec) {
  if (rec.type === "progress") return appendProgress(rec);
  if (rec.type === "question") return renderCard(rec);
  if (rec.type === "result") return appendResult(rec);
  if (rec.type === "error") return appendError(rec);
}

function connectStream() {
  const es = new EventSource("/api/studio/stream");
  es.onmessage = (e) => {
    let rec;
    try { rec = JSON.parse(e.data); } catch (_) { return; }
    dispatch(rec);
  };
  es.onerror = () => { /* browser auto-reconnects; the outbox replays on reconnect */ };
}

async function pollAgentState() {
  const box = document.getElementById("agent-status");
  try {
    const s = await fetchJSON("/api/studio/state");
    const stale = s.heartbeat_ts && (Date.now() - Date.parse(s.heartbeat_ts) > 60000);
    if (!s.attached) {
      box.textContent = "No agent connected — run /agentqa-studio in Claude Code";
      box.className = "muted";
    } else if (s.status === "waiting") {
      box.textContent = stale
        ? "Agent waiting (no heartbeat — may have disconnected)"
        : "Agent attached — waiting on you";
      box.className = stale ? "dot bad" : "dot ok";
    } else if (s.status === "running") {
      box.textContent = "Agent working…";
      box.className = "dot ok";
    } else {
      box.textContent = "Agent attached — idle";
      box.className = "dot ok";
    }
  } catch (err) {
    box.textContent = `agent state error: ${err.message}`;
  }
}

async function startJob() {
  const ideaEl = document.getElementById("job-idea");
  const idea = ideaEl.value.trim();
  if (!idea) return;
  const btn = document.getElementById("job-start");
  btn.disabled = true;
  try {
    await fetchJSON("/api/studio/job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flow_idea: idea }),
    });
    ideaEl.value = "";
    logAppend(el(`<div class="msg muted">▸ queued: ${esc(idea)}</div>`));
  } catch (err) {
    logAppend(el(`<div class="msg card"><strong class="dot bad">error</strong> ${esc(err.message)}</div>`));
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("job-start").onclick = startJob;
pollAgentState();
setInterval(pollAgentState, 4000);
connectStream();
```

- [ ] **Step 5: Append the Panel 3 styles to `style.css`**

```css
#agent-panel { grid-column: 1 / -1; }
.job-starter { display: flex; gap: 8px; margin: 8px 0; }
.job-starter input { flex: 1; font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); }
.stepper { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.step { font-size: 11px; padding: 2px 8px; border-radius: 10px; border: 1px solid var(--line); color: var(--muted); }
.step.done { color: var(--ok); border-color: var(--ok); }
.step.active { color: var(--fg); border-color: var(--fg); font-weight: 600; }
.agent-log { display: flex; flex-direction: column; gap: 8px; max-height: 420px; overflow: auto; }
.msg { padding: 2px; }
.card { background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }
.card .prompt { margin-bottom: 8px; }
.field { margin: 6px 0; display: flex; flex-direction: column; gap: 4px; }
.field input[type=text] { font: inherit; padding: 4px 8px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); }
.choices { display: flex; gap: 12px; flex-wrap: wrap; }
.card-actions { display: flex; gap: 8px; margin-top: 8px; }
.diffbox { background: #0c0d10; color: #d6d6d6; padding: 10px; border-radius: 6px; max-height: 260px; overflow: auto; white-space: pre; }
.card textarea { width: 100%; font: inherit; margin-top: 6px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); color: var(--fg); }
.locked { margin-top: 6px; }
```

- [ ] **Step 6: Run the server test file**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v`
Expected: PASS (including `test_static_assets_served`)

- [ ] **Step 7: Manual smoke (no agent needed yet)**

```bash
.devvenv/bin/python -m studio.server --repo <a repo with .agentqa/> --port 7332 --open
```
Expected: the Agent panel renders "No agent connected…"; typing an idea and
clicking Start posts a job (a "queued" line appears); the three M1 panels still
work. (The card widgets are exercised end-to-end in Task 7.)

- [ ] **Step 8: Commit (only after the user approves this task's diff)**

```bash
git add studio/static/index.html studio/static/app.js studio/static/style.css studio/tests/test_server.py
git commit -m "feat(studio): Panel 3 — agent conversation, cards, stage stepper"
```

---

### Task 7: The connector skill (`/agentqa-studio`) via skill-creator + end-to-end smoke

Author the thin transport-adapter skill and verify the whole bridge with a real
write-test job driven from the browser. **The skill is created with the
`skill-creator` skill — do not hand-write `SKILL.md`.**

**Files:**
- Create (via skill-creator): `skills/agentqa-studio/SKILL.md`
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (description: "two skills" → "three skills"), `README.md` (add the connector to the skills list)

- [ ] **Step 1: Invoke skill-creator with this brief**

Invoke the `skill-creator` skill to create `skills/agentqa-studio`. Feed it this
brief (it owns the final wording/structure):

- **name:** `agentqa-studio`
- **description:** Attach a live agent to the AgentQA Studio dashboard and drive the `agentqa-write-test` flow from the browser — watch the mailbox for a job, run the test-writing flow unchanged, and redirect its human checkpoints (clarify / build / review) and step-3 system-view asks to browser cards. Invoked as `/agentqa-studio`.
- **The skill is a transport adapter, not a re-implementation.** It MUST NOT modify or duplicate `agentqa-write-test`; it runs that flow as written and only changes *where the human questions go*.
- **The loop the skill body describes** (mechanics live in the tested `scripts/`, so the prose stays thin):
  1. **Attach.** Best-effort boot the daemon: if `nc -z 127.0.0.1 7332` fails, launch `agentqa-studio` in the background (`agentqa-studio >/tmp/agentqa-studio.log 2>&1 &` or the `bin/` launcher) so the human gets a viewer — but **do not abort if boot fails**; the job runs regardless. Then `python3 scripts/studio-attach.py <repo>`.
  2. **Watch.** `python3 scripts/studio-wait.py <repo> --job`. If the JSON says `{"status":"waiting"}`, run it again (re-block). On `{"status":"answered", ...}`, take `record.flow_idea` as the test idea.
  3. **Delegate.** Run the `agentqa-write-test` flow for that idea, exactly as written.
  4. **Redirect** each of write-test's human pause points through the mailbox instead of the terminal, using this mapping:

     | write-test pause | post (studio-post.py) | wait (studio-wait.py) |
     |---|---|---|
     | Step 2 clarify | `question --kind form --subtype clarify --prompt … --questions '<json: success/failure/blockers[/entry choice], doc answers as default>'` | `--reply-to <qid>` → apply `answers` as the clarify answers, then write `.session-requirement.md` as write-test dictates |
     | Step 3 system-view ask | `question --kind form --subtype ask --prompt … --questions '<json: one choice: Allow/Deny/Dismiss>'` | `--reply-to <qid>` → apply the chosen action |
     | Step 5 build (ONLY `build.policy: human`) | `question --kind confirm --subtype build --prompt …` | `--reply-to <qid>` → proceed once `decision == built` |
     | Step 8 review | `question --kind review --subtype review --prompt … --diff "$(git diff)" --test-files '<json: [{path,content}]>'` | `--reply-to <qid>` → `approve` proceeds to capture; `reject` feeds `note` back like a terminal rejection |

  5. **Post-back.** Emit `studio-post.py <repo> progress --text … [--stage <slug>]` at step boundaries (stages: map/clarify/explore/identifiers/build/verify/write/green/review/capture). On completion: `result --status green --summary … --test-path …`; on abandon: `result --status abandoned …` (+ `error --text …`) and let write-test's own cleanup delete the working-layer files.
  6. **Loop or detach.** After a `result`, return to step 2 (Watch) for the next job. When the user ends the session, `python3 scripts/studio-detach.py <repo>`.
- **Wherever `studio-wait` returns `{"status":"waiting"}`, run it again** — that is the single-turn re-block, not an error.
- **Reference material for skill-creator:** the scripts under `scripts/` (already built and tested in Tasks 4–5), and the design spec `docs/superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md`.

- [ ] **Step 2: Verify the skill scaffolds and its scripts still pass**

```bash
ls skills/agentqa-studio/SKILL.md
.devvenv/bin/pytest skills/agentqa-studio/tests -v
```
Expected: `SKILL.md` exists; agent-side tests PASS.

- [ ] **Step 3: Update plugin manifests + README**

Change the two `.claude-plugin/*.json` descriptions from "two skills:
agentqa-init … and agentqa-write-test …" to name the third,
`agentqa-studio` (the connector/dashboard), and add a matching line to the
`README.md` skills section. (Do not bump the plugin `version` unless the user asks.)

- [ ] **Step 4: End-to-end smoke (manual — the acceptance test)**

In a repo already configured by `/agentqa-init init` (has `.agentqa/config.yml`
and a booted simulator + app), with Appium up:

1. In a terminal: `agentqa-studio --repo <app repo>` is **not** started manually —
   instead run `/agentqa-studio` in a Claude Code session at the app repo. Confirm
   it boots the daemon (browser reachable at `http://127.0.0.1:7332/`) and the
   Agent panel shows "Agent attached — idle".
2. In the browser, type a small real flow (e.g. "log in with valid credentials")
   and click **Start**. Confirm:
   - progress lines stream and the stepper advances;
   - the **clarify** card appears with the success/failure/blocker fields (doc
     defaults pre-filled if the repo has `docs:`); submitting continues the flow;
   - under `build.policy: human`, the **build** card appears; clicking "I've built
     & installed" continues;
   - the **review** card shows the additions-only diff + the test; **Approve**
     finishes with a green `result` linking the test path.
3. Kill the Claude session mid-wait and confirm the Agent panel flips to
   "waiting (no heartbeat — may have disconnected)" within ~60s.
4. Confirm `.agentqa/studio/` is gitignored (git status shows nothing under it)
   and that `git status` shows **no** changes to `agentqa-write-test` or
   `agentqa-init`.

- [ ] **Step 5: Run the full suite**

```bash
.devvenv/bin/pytest studio/tests skills/agentqa-studio/tests -v
```
Expected: PASS (all M1 + M2 tests).

- [ ] **Step 6: Commit (only after the user approves this task's diff)**

```bash
git add skills/agentqa-studio/SKILL.md .claude-plugin/plugin.json .claude-plugin/marketplace.json README.md
git commit -m "feat(studio): /agentqa-studio connector skill (via skill-creator) + docs"
```

---

## Self-Review

**Spec coverage (M2 scope):**
- Studio Protocol v1 (JSONL, `v:1`, single-sourced) → Task 1. ✅
- Canonical fixture as executable spec, both sides test against it → Task 1 (`protocol_v1.json`), Task 4 (`test_studio_common` loads it). ✅
- `studio/mailbox.py` + endpoints (`state`/`job`/`reply`/`stream`), brainless daemon → Tasks 2, 3. ✅
- 409 concurrent-job guard → Task 3. ✅
- SSE outbox tail with reconnect replay + keepalive/disconnect probe → Tasks 2, 3. ✅
- Agent-side helper scripts (attach/post/wait/detach + `studio_common`) → Tasks 4, 5. ✅
- `studio-wait` waiting/answered in JSON, nonzero = failure; heartbeat; job cursor → Task 5. ✅
- Self-contained gitignore, no `agentqa-init`/`agentqa-write-test` change → Task 4 (`studio-attach` writes `.gitignore`), Task 7 Step 4 verification. ✅
- Panel 3: attach indicator (status-aware liveness), job starter, `stage` stepper (slug-only + graceful unknowns), four cards, bounded DOM, reconnect → Task 6. ✅
- Connector as transport adapter via skill-creator; the four-pause mapping; build card only under `build.policy: human` → Task 7. ✅
- Deferred (diagnose job, credential-prompt UI, multi-worker) → not built; none appear as tasks. ✅

**Placeholder scan:** every code step contains complete code; no TBD/TODO. The one
prose-authored artifact (`SKILL.md`) is delegated to skill-creator by explicit
constraint, with a full brief. ✅

**Type/name consistency:** `protocol.build_job/build_reply/validate/record` (Task 1)
are consumed unchanged in `mailbox.append_inbox` (Task 2) and the server routes
(Task 3). `mailbox.read_state/tail_outbox/append_inbox/studio_dir` (Task 2) match
their server usage (Task 3). `studio_common.record/post_outbox/read_inbox/read_state/write_state/studio_dir`
(Task 4) match the usage in `studio-post`/`studio-attach`/`studio-detach` (Task 4)
and `studio-wait` (Task 5). The endpoint paths and record shapes in Task 3 match
the `fetch`/`EventSource` calls and card fields in Task 6. The `stage` slug list is
identical in `progress` (Task 4/7) and the `STAGES` array (Task 6). ✅

**Naming caveat resolved:** the spec's `studio/protocol/v1.json` is realized as
`studio/protocol_v1.json` to avoid a module/package name clash with
`studio/protocol.py`; every reference in the plan uses the file name.
