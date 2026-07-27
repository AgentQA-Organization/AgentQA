"""Attaching is a takeover: one connector at a time, and a clean mailbox after.

The failure these cover is a user running /agentqa-studio twice. Before this,
the second attach left the first session's state.json behind — so the dashboard
answered every new idea with "a job is already running", the transcript still
showed cards from a dead session, and two workers polled the same inbox.
"""
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import studio_common as sc  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


attach = _load("studio-attach.py")
detach = _load("studio-detach.py")
post = _load("studio-post.py")
wait = _load("studio-wait.py")


def _attach(tmp_path, capsys):
    assert attach.main([str(tmp_path)]) == 0
    return capsys.readouterr().out.strip()


def _inbox(tmp_path):
    return sc.read_inbox(tmp_path)


def _outbox(tmp_path):
    return sc.read_jsonl(sc.studio_dir(tmp_path) / "outbox.jsonl")


def _archives(tmp_path):
    d = sc.studio_dir(tmp_path) / "archive"
    return sorted(p for p in d.iterdir()) if d.is_dir() else []


# ---- cancellation_notices: pure ------------------------------------------

def test_no_notice_when_nothing_was_attached():
    assert attach.cancellation_notices({"attached": False, "status": "idle"}) == []


def test_notice_names_the_running_job():
    [line] = attach.cancellation_notices(
        {"attached": True, "status": "running", "current_job_id": "j7"})
    assert "cancelled" in line and "j7" in line


def test_notice_explains_an_unanswerable_card():
    [line] = attach.cancellation_notices({"attached": True, "status": "waiting"})
    assert "cancelled" in line and "answered" in line


def test_idle_session_is_still_announced_as_replaced():
    [line] = attach.cancellation_notices({"attached": True, "status": "idle"})
    assert "replaced" in line


# ---- attach: identity -----------------------------------------------------

def test_attach_mints_a_connector_id(tmp_path, capsys):
    cid = _attach(tmp_path, capsys)
    assert cid and sc.read_state(tmp_path)["connector_id"] == cid


def test_second_attach_supersedes_the_first(tmp_path, capsys):
    first = _attach(tmp_path, capsys)
    second = _attach(tmp_path, capsys)
    assert first != second
    assert sc.read_state(tmp_path)["connector_id"] == second


def test_attach_leaves_state_clean(tmp_path, capsys):
    """The stale `waiting` status is what made the dashboard answer a new idea
    with 409 "a job is already running" forever after an agent walked away."""
    _attach(tmp_path, capsys)
    sc.write_state(tmp_path, status="waiting", awaiting="q1", current_job_id="j1")
    _attach(tmp_path, capsys)
    st = sc.read_state(tmp_path)
    assert st["status"] == "idle"
    assert st["awaiting"] is None
    assert st["current_job_id"] is None
    assert st["job_cursor"] is None
    assert st["attached"] is True


# ---- attach: the mailbox --------------------------------------------------

def test_attach_archives_the_previous_mailbox(tmp_path, capsys):
    _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", sc.record("job", flow_idea="old"))
    post.main([str(tmp_path), "progress", "--text", "working"])
    _attach(tmp_path, capsys)

    archives = _archives(tmp_path)
    assert len(archives) == 1
    archived = sc.read_jsonl(archives[0] / "outbox.jsonl")
    assert any(r.get("text") == "working" for r in archived)
    # …and the live outbox no longer carries the archived session's records.
    assert not any(r.get("text") == "working" for r in _outbox(tmp_path))


def test_first_attach_archives_nothing(tmp_path, capsys):
    _attach(tmp_path, capsys)
    assert _archives(tmp_path) == []
    assert _outbox(tmp_path) == []


def test_attach_posts_the_cancellation_to_the_browser(tmp_path, capsys):
    _attach(tmp_path, capsys)
    sc.write_state(tmp_path, status="running", current_job_id="j9")
    _attach(tmp_path, capsys)
    out = _outbox(tmp_path)
    assert any(r["type"] == "error" and "j9" in r["text"] for r in out), out
    # The stepper must be released too, or the dashboard shows a job in flight.
    assert any(r["type"] == "result" and r["status"] == "abandoned" for r in out), out


def test_attach_does_not_announce_a_job_that_already_finished(tmp_path, capsys):
    _attach(tmp_path, capsys)
    post.main([str(tmp_path), "result", "--status", "green", "--summary", "done"])
    capsys.readouterr()
    _attach(tmp_path, capsys)
    assert not any(r["type"] == "result" for r in _outbox(tmp_path))


# ---- attach: queued jobs survive -----------------------------------------

def test_attach_carries_an_unclaimed_job_forward(tmp_path, capsys):
    """Typing the idea in the dashboard and *then* running /agentqa-studio is
    the normal way to start a job — the attach must not throw that away."""
    _attach(tmp_path, capsys)
    job = sc.record("job", flow_idea="log in with a valid account")
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", job)
    _attach(tmp_path, capsys)

    carried = [r for r in _inbox(tmp_path) if r["type"] == "job"]
    assert [r["flow_idea"] for r in carried] == ["log in with a valid account"]
    assert carried[0]["id"] == job["id"]
    # The fresh cursor must let the new wait actually find it.
    assert sc.read_state(tmp_path)["job_cursor"] is None
    assert wait._find_job(tmp_path)["id"] == job["id"]


def test_attach_drops_a_job_the_old_session_already_claimed(tmp_path, capsys):
    _attach(tmp_path, capsys)
    done = sc.record("job", flow_idea="already ran")
    queued = sc.record("job", flow_idea="never started")
    for r in (done, queued):
        sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", r)
    sc.write_state(tmp_path, job_cursor=done["id"], status="running",
                   current_job_id=done["id"])
    _attach(tmp_path, capsys)

    assert [r["flow_idea"] for r in _inbox(tmp_path) if r["type"] == "job"] \
        == ["never started"]


def test_attach_drops_stale_replies(tmp_path, capsys):
    """A reply to a card from the archived session must not be visible to the
    new one — the new agent's wait would match it and skip a real question."""
    _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl",
                   sc.record("reply", reply_to="q1", decision="approve"))
    _attach(tmp_path, capsys)
    assert wait._find_reply(tmp_path, "q1") is None


def test_carried_job_is_announced_in_the_new_transcript(tmp_path, capsys):
    _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl",
                   sc.record("job", flow_idea="guest checkout"))
    _attach(tmp_path, capsys)
    assert any("guest checkout" in (r.get("text") or "") for r in _outbox(tmp_path))


# ---- the displaced worker stops ------------------------------------------

def test_wait_reports_superseded_instead_of_claiming_a_job(tmp_path, capsys):
    old = _attach(tmp_path, capsys)
    new = _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", sc.record("job", flow_idea="x"))

    rc = wait.main([str(tmp_path), "--job", "--timeout", "0", "--poll", "0",
                    "--connector", old])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "superseded" and out["connector_id"] == new
    # The live session's state is untouched: no job claimed, still idle.
    st = sc.read_state(tmp_path)
    assert st["status"] == "idle" and st["job_cursor"] is None


def test_superseded_wait_does_not_swallow_the_new_sessions_reply(tmp_path, capsys):
    """Waiting on a reply writes no state, so nothing would have caught the
    takeover on this path: the displaced worker would read the answer the user
    gave the *new* session's card and act on it as if it were its own."""
    old = _attach(tmp_path, capsys)
    _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl",
                   sc.record("reply", reply_to="q1", decision="approve"))

    rc = wait.main([str(tmp_path), "--reply-to", "q1", "--timeout", "0",
                    "--poll", "0", "--connector", old])
    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip())["status"] == "superseded"


def test_wait_proceeds_for_the_current_connector(tmp_path, capsys):
    cid = _attach(tmp_path, capsys)
    sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", sc.record("job", flow_idea="x"))
    wait.main([str(tmp_path), "--job", "--timeout", "0", "--poll", "0", "--connector", cid])
    assert json.loads(capsys.readouterr().out.strip())["status"] == "answered"


def test_a_blocked_wait_stops_when_a_second_connector_attaches(tmp_path, capsys):
    """The real race: the old agent is sitting in an 8-minute wait when the user
    runs /agentqa-studio again in another window. It passed no --connector, so
    it has to notice the takeover from the id it captured at startup — otherwise
    it goes on claiming jobs meant for the session that replaced it."""
    _attach(tmp_path, capsys)
    done = []

    def blocked_wait():
        done.append(wait.main([str(tmp_path), "--job", "--timeout", "10", "--poll", "0.02"]))

    t = threading.Thread(target=blocked_wait)
    t.start()
    time.sleep(0.2)                       # let it get into the poll loop
    _attach(tmp_path, capsys)             # the takeover, mid-wait
    t.join(timeout=10)

    assert not t.is_alive(), "the displaced wait never stopped"
    assert done == [0]
    assert "superseded" in capsys.readouterr().out


def test_post_is_refused_after_being_superseded(tmp_path, capsys):
    old = _attach(tmp_path, capsys)
    _attach(tmp_path, capsys)
    before = len(_outbox(tmp_path))
    rc = post.main([str(tmp_path), "progress", "--text", "ghost", "--connector", old])
    assert rc == 3
    assert "superseded" in capsys.readouterr().err
    assert len(_outbox(tmp_path)) == before, "a displaced worker wrote to the live outbox"


def test_post_works_for_the_current_connector(tmp_path, capsys):
    cid = _attach(tmp_path, capsys)
    assert post.main([str(tmp_path), "progress", "--text", "ok", "--connector", cid]) == 0
    assert any(r.get("text") == "ok" for r in _outbox(tmp_path))


def test_detach_from_a_displaced_session_leaves_the_live_one_attached(tmp_path, capsys):
    old = _attach(tmp_path, capsys)
    _attach(tmp_path, capsys)
    assert detach.main([str(tmp_path), "--connector", old]) == 0
    assert sc.read_state(tmp_path)["attached"] is True


def test_detach_works_for_the_current_connector(tmp_path, capsys):
    cid = _attach(tmp_path, capsys)
    assert detach.main([str(tmp_path), "--connector", cid]) == 0
    assert sc.read_state(tmp_path)["attached"] is False


# ---- studio_common primitives --------------------------------------------

def test_write_state_refuses_a_superseded_connector(tmp_path, capsys):
    old = _attach(tmp_path, capsys)
    _attach(tmp_path, capsys)
    with pytest.raises(sc.Superseded):
        sc.write_state(tmp_path, connector=old, status="running")


def test_write_state_without_a_connector_is_unconditional(tmp_path, capsys):
    _attach(tmp_path, capsys)
    assert sc.write_state(tmp_path, status="running")["status"] == "running"


def test_unconsumed_jobs_returns_everything_for_an_unknown_cursor():
    jobs = [{"type": "job", "id": "a"}, {"type": "job", "id": "b"}]
    assert sc.unconsumed_jobs(jobs, "from-an-older-inbox") == jobs
    assert sc.unconsumed_jobs(jobs, None) == jobs
    assert sc.unconsumed_jobs(jobs, "a") == [jobs[1]]
    assert sc.unconsumed_jobs(jobs, "b") == []


def test_archive_mailbox_is_a_noop_on_an_empty_dir(tmp_path):
    assert sc.archive_mailbox(tmp_path) is None


def test_two_attaches_in_the_same_second_do_not_collide(tmp_path, capsys):
    for _ in range(3):
        sc.append_line(sc.studio_dir(tmp_path) / "inbox.jsonl", sc.record("job", flow_idea="x"))
        _attach(tmp_path, capsys)
    assert len(_archives(tmp_path)) == 3
