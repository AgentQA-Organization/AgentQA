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
