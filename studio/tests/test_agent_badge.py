"""The attach badge's pure decision function, exercised through node.

`attachView` is the one piece of app.js worth pinning in a test: it decides
whether the dashboard tells you an agent is alive. Getting it wrong is silent —
the browser cheerfully reports a healthy agent while a queued job rots in the
inbox with nothing polling for it. Everything else in app.js is DOM painting.

The function is sliced out of the shipped app.js by brace matching and evaluated
as-is, so the test can never drift from the file the daemon actually serves.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _slice_fn(src: str, name: str) -> str:
    """Return the source of `function <name>(…) {…}`, matched by brace depth."""
    start = src.index("function %s(" % name)
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces in %s" % name)


def attach_view(state, now_ms):
    """Evaluate app.js's attachView(state, now) in node and return its result."""
    src = APP_JS.read_text(encoding="utf-8")
    const = [ln for ln in src.split("\n") if ln.startswith("const HEARTBEAT_STALE_MS")]
    assert const, "HEARTBEAT_STALE_MS must be a top-level const in app.js"
    script = "%s\n%s\nconsole.log(JSON.stringify(attachView(%s, %d)));" % (
        const[0], _slice_fn(src, "attachView"), json.dumps(state), now_ms,
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


NOW = 1_800_000_000_000          # fixed "now" in ms
FRESH = "2027-01-15T10:00:00Z"   # ~now
STALE = "2027-01-15T09:00:00Z"   # an hour before now


def _now_for(ts):
    """Node parses the ISO stamps; anchor `now` a few seconds past FRESH."""
    out = subprocess.run(
        ["node", "-e", "console.log(Date.parse(%s) + 5000)" % json.dumps(ts)],
        capture_output=True, text=True,
    )
    return int(out.stdout.strip())


def test_detached_reads_disconnected():
    v = attach_view({"attached": False, "status": "idle"}, NOW)
    assert v["state"] == "disconnected"
    assert "/agentqa-studio" in v["text"]


def test_live_idle_reads_idle():
    v = attach_view({"attached": True, "status": "idle", "heartbeat_ts": FRESH},
                    _now_for(FRESH))
    assert v["state"] == "idle"
    assert v["dot"] is None


def test_idle_with_dead_heartbeat_is_stale_not_idle():
    """The bug: an agent that attached and then went away kept reading as a
    healthy 'Agent attached — idle', so a queued job looked like it was being
    worked on when nothing was polling the inbox at all."""
    v = attach_view({"attached": True, "status": "idle", "heartbeat_ts": STALE},
                    _now_for(FRESH))
    assert v["state"] == "stale"
    assert v["dot"] == "alert"


def test_waiting_with_dead_heartbeat_is_stale():
    v = attach_view({"attached": True, "status": "waiting", "heartbeat_ts": STALE},
                    _now_for(FRESH))
    assert v["state"] == "stale"


def test_live_waiting_reads_waiting():
    v = attach_view({"attached": True, "status": "waiting", "heartbeat_ts": FRESH},
                    _now_for(FRESH))
    assert v["state"] == "waiting"
    assert v["dot"] == "alert"


def test_running_never_reads_stale():
    """A running agent is off driving the device for minutes at a stretch — no
    poll loop is bumping the heartbeat, so an old stamp there means nothing."""
    v = attach_view({"attached": True, "status": "running", "heartbeat_ts": STALE},
                    _now_for(FRESH))
    assert v["state"] == "running"
    assert v["dot"] == "busy"


def test_missing_heartbeat_is_not_treated_as_stale():
    v = attach_view({"attached": True, "status": "idle"}, NOW)
    assert v["state"] == "idle"
