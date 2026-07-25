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
