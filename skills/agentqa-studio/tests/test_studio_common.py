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


def test_write_before_attach_creates_gitignore(tmp_path):
    # Calling post_outbox without prior attach should create .gitignore
    sc.post_outbox(tmp_path, sc.record("progress", text="x"))
    assert (sc.studio_dir(tmp_path) / ".gitignore").read_text().strip() == "*"


def test_write_state_before_attach_creates_gitignore(tmp_path):
    # Calling write_state without prior attach should create .gitignore
    sc.write_state(tmp_path, status="running")
    assert (sc.studio_dir(tmp_path) / ".gitignore").read_text().strip() == "*"
