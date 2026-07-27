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


def test_permission_subtype_is_valid():
    """The permission bridge posts questions with this subtype; validate() must
    accept them or the hook's post is rejected at the mailbox boundary."""
    rec = {"v": 1, "id": "qp", "ts": "2026-07-27T00:00:00Z", "type": "question",
           "kind": "review", "subtype": "permission",
           "prompt": "Agent wants to edit Home.swift"}
    assert protocol.validate(rec) is rec
