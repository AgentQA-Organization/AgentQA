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
