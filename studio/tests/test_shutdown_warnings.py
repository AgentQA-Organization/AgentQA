"""The stop-server confirm dialog's pure decision function, exercised through node.

`shutdownWarnings` decides what the confirm dialog tells you is still in flight
before you kill the daemon. Getting it wrong loses work silently: stopping mid
`waiting` strands the agent on a question nobody can answer, and stopping mid run
orphans a pytest child. Everything else in the stop flow is DOM painting.

Sliced out of the shipped app.js and evaluated as-is, like test_agent_badge.py,
so the test can never drift from the file the daemon actually serves.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

WARN_JOB = "running a job"
WARN_WAIT = "waiting on your answer"
WARN_RUN = "pytest run"


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


def warnings_for(state, run_active):
    """Evaluate app.js's shutdownWarnings(state, runActive) in node."""
    src = APP_JS.read_text(encoding="utf-8")
    script = "%s\nconsole.log(JSON.stringify(shutdownWarnings(%s, %s)));" % (
        _slice_fn(src, "shutdownWarnings"),
        json.dumps(state), "true" if run_active else "false",
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_idle_agent_and_no_run_warns_about_nothing():
    assert warnings_for({"attached": True, "status": "idle"}, False) == []


def test_running_agent_warns_about_the_job():
    w = warnings_for({"attached": True, "status": "running"}, False)
    assert len(w) == 1 and WARN_JOB in w[0]


def test_waiting_agent_warns_the_question_becomes_unanswerable():
    w = warnings_for({"attached": True, "status": "waiting"}, False)
    assert len(w) == 1 and WARN_WAIT in w[0]


def test_active_run_warns_the_test_process_is_left_behind():
    w = warnings_for({"attached": True, "status": "idle"}, True)
    assert len(w) == 1 and WARN_RUN in w[0]


def test_busy_agent_and_active_run_warn_separately():
    w = warnings_for({"attached": True, "status": "waiting"}, True)
    assert len(w) == 2
    assert any(WARN_WAIT in x for x in w) and any(WARN_RUN in x for x in w)


def test_detached_agent_is_not_warned_about():
    """A stale state.json can still read `running` long after the agent left —
    `attached` is what says someone is home, so a detached agent is not work
    in flight and must not be reported as such."""
    assert warnings_for({"attached": False, "status": "running"}, False) == []
