from pathlib import Path

import pytest

from studio import mailbox, protocol


def test_append_inbox_validates_and_writes(tmp_path):
    rec = mailbox.append_inbox(tmp_path, protocol.build_job("log in"))
    line = (mailbox.studio_dir(tmp_path) / "inbox.jsonl").read_text().strip()
    assert '"type": "job"' in line
    assert rec["flow_idea"] == "log in"


def test_append_inbox_creates_gitignore(tmp_path):
    mailbox.append_inbox(tmp_path, protocol.build_job("x"))
    gi = mailbox.studio_dir(tmp_path) / ".gitignore"
    assert gi.read_text().strip() == "*"


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


def test_read_state_default_when_corrupt(tmp_path):
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "state.json").write_text('{"v":1,"attached":true')  # truncated/invalid JSON
    st = mailbox.read_state(tmp_path)
    assert st["attached"] is False
    assert st["status"] == "idle"
    assert st["current_job_id"] is None
    assert st["awaiting"] is None
    assert st["heartbeat_ts"] is None
    assert st["job_cursor"] is None


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


def test_tail_outbox_restarts_when_the_file_is_rotated(tmp_path):
    """A new connector archives the outbox mid-stream. The tail follows the file
    by line offset, so without this it would sit silent until the fresh file
    grew past the old one's length — the new session's first records, the ones
    explaining what just happened, would never reach the browser."""
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    out = d / "outbox.jsonl"
    out.write_text('{"a": 1}\n{"b": 2}\n{"c": 3}\n')
    it = mailbox.tail_outbox(tmp_path, poll=0.01)
    for _ in range(3):
        next(it)
    assert next(it) is None

    out.write_text('{"fresh": 1}\n')     # shorter: the archive + a new session
    assert next(it) is mailbox.OUTBOX_RESET
    assert next(it) == {"fresh": 1}


def test_tail_outbox_survives_the_outbox_being_deleted(tmp_path):
    d = mailbox.studio_dir(tmp_path)
    d.mkdir(parents=True)
    out = d / "outbox.jsonl"
    out.write_text('{"a": 1}\n')
    it = mailbox.tail_outbox(tmp_path, poll=0.01)
    assert next(it) == {"a": 1}
    out.unlink()
    assert next(it) is mailbox.OUTBOX_RESET
    assert next(it) is None
