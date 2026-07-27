import json
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Thread

import pytest

from studio.server import make_server


@pytest.fixture
def live_server(tmp_path):
    cfgdir = tmp_path / ".agentqa"
    cfgdir.mkdir()
    (cfgdir / "config.yml").write_text(textwrap.dedent("""\
        platform: ios
        bundle_id: com.acme.app
        test_dir: AutomationTests
        build:
          policy: human
        reset_app_data: always
        appium:
          port: 4723
    """))
    (tmp_path / ".agentqa" / "memory" / "flows").mkdir(parents=True)
    (tmp_path / ".agentqa" / "memory" / "flows" / "login.md").write_text("# login\n")
    srv = make_server(tmp_path, memory_scripts=None, port=0)
    Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    yield "http://127.0.0.1:%d" % port
    srv.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read().decode()


def test_config_endpoint(live_server):
    status, body = _get(live_server, "/api/config")
    assert status == 200
    data = json.loads(body)
    assert data["app_id"] == "com.acme.app"
    assert data["build_policy"] == "human"


def test_memory_endpoint_lists_flow(live_server):
    status, body = _get(live_server, "/api/memory")
    assert status == 200
    assert "login" in json.loads(body)["flows"]


def test_index_served(live_server):
    status, body = _get(live_server, "/")
    assert status == 200
    assert "AgentQA Studio" in body


def test_unknown_route_404(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(live_server, "/api/nope")
    assert exc.value.code == 404


def test_run_rejects_unknown_target(live_server):
    import urllib.request, json as _json
    req = urllib.request.Request(
        live_server + "/api/run", method="POST",
        data=_json.dumps({"target": "../../etc/passwd", "env": {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected HTTP 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_post_malformed_body_returns_400(live_server):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(
        live_server + "/api/run", method="POST",
        data=b"not json", headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        assert False, "expected HTTP 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_post_missing_config_returns_500(tmp_path):
    import json as _json
    import urllib.request
    import urllib.error
    from threading import Thread
    from studio.server import make_server
    # tmp_path has NO .agentqa/config.yml
    srv = make_server(tmp_path, memory_scripts=None, port=0)
    Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        req = urllib.request.Request(
            base + "/api/run", method="POST",
            data=_json.dumps({"target": "all"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "expected HTTP 500"
        except urllib.error.HTTPError as e:
            assert e.code == 500
    finally:
        srv.shutdown()


def test_static_assets_served(live_server):
    for asset, needle in [
        ("/static/app.js", "connectStream"),
        ("/static/style.css", ".stepper"),
    ]:
        status, body = _get(live_server, asset)
        assert status == 200, asset
        assert needle in body, asset


def test_memory_stale_endpoint_none_without_scripts(live_server):
    status, body = _get(live_server, "/api/memory/stale")
    assert status == 200
    assert json.loads(body)["stale"] is None


def test_memory_lint_endpoint_none_without_scripts(live_server):
    status, body = _get(live_server, "/api/memory/lint")
    assert status == 200
    assert json.loads(body)["lint"] is None


def _post(base, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def _studio_dir(tmp):
    from studio import mailbox
    return mailbox.studio_dir(tmp)


def test_studio_state_default(live_server):
    status, body = _get(live_server, "/api/studio/state")
    assert status == 200
    assert json.loads(body)["attached"] is False


def test_studio_job_appends_to_inbox(live_server, tmp_path):
    status, body = _post(live_server, "/api/studio/job", {"flow_idea": "log in"})
    assert status == 200 and body["ok"] is True
    inbox = (_studio_dir(tmp_path) / "inbox.jsonl").read_text()
    assert '"type": "job"' in inbox and "log in" in inbox


def test_studio_job_409_when_running(live_server, tmp_path):
    d = _studio_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text('{"v":1,"attached":true,"status":"running"}')
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(live_server, "/api/studio/job", {"flow_idea": "x"})
    assert exc.value.code == 409


def test_studio_reply_appends(live_server, tmp_path):
    status, body = _post(
        live_server, "/api/studio/reply", {"reply_to": "q1", "decision": "built"})
    assert status == 200
    inbox = (_studio_dir(tmp_path) / "inbox.jsonl").read_text()
    assert '"type": "reply"' in inbox and '"reply_to": "q1"' in inbox


def test_studio_stream_replays_outbox(live_server, tmp_path):
    d = _studio_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / "outbox.jsonl").write_text('{"type":"progress","text":"hi"}\n')
    with urllib.request.urlopen(live_server + "/api/studio/stream", timeout=5) as r:
        for _ in range(20):
            line = r.readline().decode()
            if line.startswith("data:"):
                assert '"text":"hi"' in line or '"text": "hi"' in line
                return
    assert False, "no data event received"


# The shutdown endpoint kills the server it is served by, so these tests own the
# serve_forever thread rather than borrowing the fixture's (which yields only a URL).
def test_shutdown_answers_then_stops_serving(tmp_path):
    srv = make_server(tmp_path, memory_scripts=None, port=0)
    loop = Thread(target=srv.serve_forever, daemon=True)
    loop.start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        # The response must land before the socket goes away — a browser that
        # never sees the 200 cannot tell "stopped" from "endpoint is missing".
        status, body = _post(base, "/api/shutdown", {})
        assert status == 200 and body["ok"] is True
        loop.join(timeout=5)
        assert not loop.is_alive(), "serve_forever still running after /api/shutdown"
    finally:
        srv.shutdown()
        srv.server_close()


def test_shutdown_releases_the_port(tmp_path):
    """The listening socket must be closed too, not just the accept loop — an
    open socket keeps the port claimed and leaves the next request hanging in
    the backlog instead of failing fast."""
    srv = make_server(tmp_path, memory_scripts=None, port=0)
    Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        _post(base, "/api/shutdown", {})
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                _get(base, "/api/config")
            except urllib.error.URLError:
                return
            except OSError:
                return
            time.sleep(0.1)
        assert False, "port still accepting requests after /api/shutdown"
    finally:
        srv.server_close()
