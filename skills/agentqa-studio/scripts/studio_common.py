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


class Superseded(RuntimeError):
    """This worker's connector id is no longer the attached one.

    Raised when a newer /agentqa-studio attach has taken over the mailbox. The
    displaced worker must stop writing — every file here is shared, so a stale
    worker that keeps posting corrupts the live session's transcript.
    """


def studio_dir(repo_root):
    return Path(repo_root) / ".agentqa" / "studio"


def ensure_mailbox(repo_root):
    """Ensure mailbox dir exists with .gitignore = "*"; called before every write."""
    d = studio_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text("*\n", encoding="utf-8")
    return d


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
    ensure_mailbox(repo_root)
    append_line(studio_dir(repo_root) / "outbox.jsonl", rec)
    return rec


def read_jsonl(path):
    """Read whole records from a .jsonl file; a partial trailing line is skipped."""
    path = Path(path)
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


def read_inbox(repo_root):
    return read_jsonl(studio_dir(repo_root) / "inbox.jsonl")


def read_state(repo_root):
    path = studio_dir(repo_root) / "state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def write_state(repo_root, connector=None, **updates):
    """Merge updates into state.json; always stamp v and a fresh heartbeat.

    Pass `connector` to make the write conditional on still being the attached
    connector — a displaced worker must not bump the live session's heartbeat.
    """
    check_connector(repo_root, connector)
    state = read_state(repo_root)
    state.update(updates)
    state["v"] = PROTOCOL_VERSION
    state.setdefault("attached", True)
    state["heartbeat_ts"] = now_ts()
    return _persist_state(repo_root, state)


def reset_state(repo_root, **fields):
    """Replace state.json outright — nothing from the old session survives.

    Attach uses this rather than write_state: merging would carry a displaced
    session's keys (a dangling `awaiting`, a `current_job_id` for a job nobody
    is running) into the new one, which is exactly the stale state that makes
    the dashboard refuse a new job with "a job is already running".
    """
    state = {"v": PROTOCOL_VERSION, "connector_id": None, "attached": True,
             "status": "idle", "current_job_id": None, "awaiting": None,
             "job_cursor": None}
    state.update(fields)
    state["heartbeat_ts"] = now_ts()
    return _persist_state(repo_root, state)


def _persist_state(repo_root, state):
    d = ensure_mailbox(repo_root)
    (d / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


# ---- one connector at a time -------------------------------------------

def new_connector_id():
    return uuid.uuid4().hex


def check_connector(repo_root, connector):
    """Raise Superseded if `connector` is no longer the attached connector.

    A missing id on either side means "not participating": state written before
    this existed, or a caller that did not pass one, both keep the old
    unconditional behaviour instead of failing closed on nothing.
    """
    if not connector:
        return None
    live = read_state(repo_root).get("connector_id")
    if live and live != connector:
        raise Superseded(live)
    return live


def archive_mailbox(repo_root):
    """Move inbox/outbox aside into archive/<ts>/; return the dir, or None.

    The rename is atomic and happens before anything reads the old files, so a
    record written by a worker still holding the old path either lands in the
    file we archive (and is read from there) or in the fresh one — never in a
    gap between the two.
    """
    d = ensure_mailbox(repo_root)
    names = [n for n in ("inbox.jsonl", "outbox.jsonl") if (d / n).is_file()]
    if not names:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = d / "archive" / stamp
    n = 1
    while dest.exists():            # two attaches inside the same second
        n += 1
        dest = d / "archive" / ("%s-%d" % (stamp, n))
    dest.mkdir(parents=True)
    for name in names:
        os.replace(str(d / name), str(dest / name))
    return dest


def unconsumed_jobs(records, job_cursor):
    """The jobs in `records` that no session ever claimed.

    `job_cursor` is the last job a worker started, so everything after it was
    only ever queued. A cursor that is absent from `records` pointed into an
    even older, already-archived inbox — nothing here was claimed, so it all
    carries forward.
    """
    jobs = [r for r in records if r.get("type") == "job"]
    ids = [j.get("id") for j in jobs]
    if not job_cursor or job_cursor not in ids:
        return jobs
    return jobs[ids.index(job_cursor) + 1:]
