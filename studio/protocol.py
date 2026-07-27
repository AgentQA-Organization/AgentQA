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


def build_job(flow_idea: str, requirements: Any = None) -> Dict[str, Any]:
    """A job, optionally carrying the requirements document uploaded with it.

    `requirements` is `{name, path, chars}` — the user's filename, a repo-relative
    path into the mailbox, and its size. The record carries a pointer, not the
    text: a requirements doc is thousands of characters and inbox.jsonl is read
    whole on every poll.
    """
    if requirements:
        return record("job", flow_idea=flow_idea, requirements=requirements)
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
    if t == "job":
        if not rec.get("flow_idea"):
            raise ProtocolError("job missing flow_idea")
        req = rec.get("requirements")
        if req is not None:
            if not isinstance(req, dict) or not req.get("name") or not req.get("path"):
                raise ProtocolError("job requirements need a name and a path")
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
