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
