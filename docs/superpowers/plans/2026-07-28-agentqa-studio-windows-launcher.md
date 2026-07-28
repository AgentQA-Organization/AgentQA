# AgentQA Studio Windows Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/agentqa-studio` boot its dashboard daemon reliably from native Windows (PowerShell/cmd.exe), with zero behavior change on macOS/Linux.

**Architecture:** Move all "boot the daemon if it isn't up" logic out of the bash-only SKILL.md snippet and `bin/agentqa-studio`'s reach, into one new stdlib-only Python script, `skills/agentqa-studio/scripts/studio-launch.py`. SKILL.md calls it with a single flat `python3 script.py <repo>` command — the one command shape proven (in the bug report's own transcript) to translate correctly across bash, PowerShell, and cmd.exe. A thin new `bin/agentqa-studio.cmd` gives Windows users the same direct, human-invoked launcher that `bin/agentqa-studio` already gives POSIX users, by delegating to the same script's `--foreground` mode.

**Tech Stack:** Python 3 stdlib only (`argparse`, `socket`, `subprocess`, `sys`, `os`, `tempfile`, `time`, `pathlib`). Tests with `pytest`, following this repo's existing pattern of loading hyphenated script files via `importlib.util`.

**Design spec:** [`docs/superpowers/specs/2026-07-28-agentqa-studio-windows-launcher-design.md`](../specs/2026-07-28-agentqa-studio-windows-launcher-design.md)

## Global Constraints

- Default dashboard port: `7332`, overridable via the `AGENTQA_STUDIO_PORT` env var or `--port` — same convention as `bin/agentqa-studio`.
- Detached-boot status poll: up to `2.0s` total, `0.2s` between checks.
- Launcher log file: `<tempfile.gettempdir()>/agentqa-studio.log` — never a hardcoded `/tmp` path.
- `studio-launch.py`'s default (non-`--foreground`) mode **always exits 0** — booting the dashboard is best-effort; this script must never be the reason a job aborts.
- `bin/agentqa-studio` (POSIX/bash) is **not modified** — it already works and is tested.
- No automated `PATH` or Windows registry mutation. Print instructions; the user applies them by hand — matches the existing (also manual) POSIX convention.
- stdlib only. No new third-party dependencies.
- `STUDIO_ROOT` (the plugin root containing `bin/`, `studio/`, `skills/`) resolves as `Path(__file__).resolve().parents[3]` from `skills/agentqa-studio/scripts/studio-launch.py`.
- `MEM_SCRIPTS` candidates, checked in order, first containing `memory-index.py` wins: `STUDIO_ROOT/skills/agentqa-write-test/scripts`, `~/.claude/skills/agentqa-write-test/scripts`, `<repo>/.claude/skills/agentqa-write-test/scripts` — ported from `bin/agentqa-studio`'s existing bash loop.
- Windows-only `subprocess` constants (`CREATE_NEW_PROCESS_GROUP`, `DETACHED_PROCESS`) do not exist as attributes on non-Windows CPython builds — referencing them directly breaks on macOS/Linux even inside an `if sys.platform == "win32":` branch, because the branch's *body* still has to be importable/testable on this dev machine. Precompute them at module level with `getattr(subprocess, "NAME", <documented literal>)` (`CREATE_NEW_PROCESS_GROUP = 0x00000200`, `DETACHED_PROCESS = 0x00000008`) so the values are correct on real Windows and the module still imports and tests cleanly on macOS.

---

### Task 1: `studio-launch.py` — the cross-platform launcher

**Files:**
- Create: `skills/agentqa-studio/scripts/studio-launch.py`
- Test: `skills/agentqa-studio/tests/test_studio_launch.py`

**Interfaces:**
- Consumes: nothing from other tasks — this is the foundation.
- Produces (the CLI contract Tasks 2 and 3 depend on):
  - `python3 studio-launch.py <repo> [--port N] [--memory-scripts PATH]` — idempotent, best-effort, detached boot. Prints one line to stdout: `already-running`, `started`, or `started (port not open after 2.0s -- see log at <path>)`. Always exits `0`.
  - `python3 studio-launch.py <repo> [--port N] [--memory-scripts PATH] --foreground` — runs the daemon as a direct child, blocks, returns its exit code.
  - `--port` defaults to the `AGENTQA_STUDIO_PORT` env var, or `7332`.

- [ ] **Step 1: Write the failing tests for the pure helpers**

Create `skills/agentqa-studio/tests/test_studio_launch.py`:

```python
import socket
import sys
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


launch = _load("studio-launch.py")


def _listening_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s


def test_port_open_true_when_listening():
    s = _listening_socket()
    try:
        port = s.getsockname()[1]
        assert launch.port_open(port) is True
    finally:
        s.close()


def test_port_open_false_when_nothing_listening():
    s = _listening_socket()
    port = s.getsockname()[1]
    s.close()   # port now free
    assert launch.port_open(port) is False


def test_find_memory_scripts_matches_first_candidate_with_marker(tmp_path):
    studio_root = tmp_path / "studio_root"
    write_test_scripts = studio_root / "skills" / "agentqa-write-test" / "scripts"
    write_test_scripts.mkdir(parents=True)
    (write_test_scripts / "memory-index.py").write_text("# marker\n")
    found = launch.find_memory_scripts(tmp_path / "some-repo", studio_root=studio_root)
    assert found == write_test_scripts


def test_find_memory_scripts_none_when_no_candidate_has_marker(tmp_path):
    found = launch.find_memory_scripts(tmp_path / "some-repo", studio_root=tmp_path / "nowhere")
    assert found is None


def test_server_argv_without_memory_scripts():
    argv = launch.server_argv("/repo", 7332, None)
    assert argv == [sys.executable, "-m", "studio.server",
                     "--repo", "/repo", "--port", "7332", "--open"]


def test_server_argv_with_memory_scripts():
    argv = launch.server_argv("/repo", 7332, Path("/mem/scripts"))
    assert argv[-2:] == ["--memory-scripts", "/mem/scripts"]


def test_env_prepends_studio_root_to_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/existing")
    env = launch._env()
    assert env["PYTHONPATH"] == str(launch.STUDIO_ROOT) + launch.os.pathsep + "/existing"


def test_env_sets_pythonpath_when_unset(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = launch._env()
    assert env["PYTHONPATH"] == str(launch.STUDIO_ROOT)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py -v`
Expected: collection error / `FileNotFoundError` — `studio-launch.py` does not exist yet.

- [ ] **Step 3: Implement the pure helpers**

Create `skills/agentqa-studio/scripts/studio-launch.py`:

```python
#!/usr/bin/env python3
"""Best-effort cross-platform boot for the Studio dashboard daemon.

  studio-launch.py <repo>                  # idempotent: start the daemon detached if
                                            # its port isn't already open; never blocks
  studio-launch.py <repo> --foreground     # run the daemon as a direct child and block
                                            # (Ctrl-C stops it) -- for a human at a prompt

Replaces the bash-only "check the port, background the launcher, log to /tmp"
snippet that used to live inline in SKILL.md step 1. A single
`python3 studio-launch.py <repo>` call is the one shell-agnostic command that
survives translation into PowerShell/cmd.exe as well as bash -- see the design
spec's "evidence for the fix direction" section.

Prints one line to stdout:
  already-running                          the port was already open; nothing spawned
  started                                  spawned and the port came up within ~2s
  started (port not open after 2.0s -- see log at <path>)
                                            spawned, but couldn't confirm before giving up

Booting is best-effort: the default mode always exits 0 (real usage errors from
argparse aside), because the mailbox files are the source of truth and a job
must never abort just because the dashboard failed to come up.
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PORT = 7332
POLL_TIMEOUT = 2.0
POLL_INTERVAL = 0.2

# subprocess.CREATE_NEW_PROCESS_GROUP / DETACHED_PROCESS only exist as attributes
# on Windows CPython builds. Precompute them with their documented literal values
# so this module still imports (and is testable) on macOS/Linux; on real Windows
# getattr just returns the real, identical constant.
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


def find_memory_scripts(repo, studio_root=STUDIO_ROOT):
    for cand in (
        studio_root / "skills" / "agentqa-write-test" / "scripts",
        Path.home() / ".claude" / "skills" / "agentqa-write-test" / "scripts",
        Path(repo) / ".claude" / "skills" / "agentqa-write-test" / "scripts",
    ):
        if (cand / "memory-index.py").is_file():
            return cand
    return None


def server_argv(repo, port, memory_scripts):
    argv = [sys.executable, "-m", "studio.server",
            "--repo", str(repo), "--port", str(port), "--open"]
    if memory_scripts:
        argv += ["--memory-scripts", str(memory_scripts)]
    return argv


def _env():
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(STUDIO_ROOT) + (os.pathsep + existing if existing else "")
    return env
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Write the failing tests for the CLI (foreground + detached boot)**

Append to `skills/agentqa-studio/tests/test_studio_launch.py`:

```python
def test_popen_kwargs_windows(monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "win32")
    kwargs = launch._popen_kwargs("LOGFILE")
    assert kwargs["creationflags"] == launch._CREATE_NEW_PROCESS_GROUP | launch._DETACHED_PROCESS
    assert "start_new_session" not in kwargs
    assert kwargs["stdout"] == "LOGFILE" and kwargs["stderr"] == "LOGFILE"


def test_popen_kwargs_posix(monkeypatch):
    monkeypatch.setattr(launch.sys, "platform", "darwin")
    kwargs = launch._popen_kwargs("LOGFILE")
    assert kwargs["start_new_session"] is True
    assert "creationflags" not in kwargs


def test_launch_detached_reports_started_once_port_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    calls = []
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    seq = iter([False, False, True])
    monkeypatch.setattr(launch, "port_open", lambda port, host="127.0.0.1": next(seq))
    monkeypatch.setattr(launch, "POLL_INTERVAL", 0.01)
    result = launch.launch_detached("/repo", 7332, None)
    assert result == "started"
    assert len(calls) == 1
    call_args, call_kwargs = calls[0]
    assert call_args[0] == launch.server_argv("/repo", 7332, None)


def test_launch_detached_reports_timeout_when_port_never_opens(monkeypatch, tmp_path):
    monkeypatch.setattr(launch.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(launch.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(launch, "port_open", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(launch, "POLL_TIMEOUT", 0.05)
    monkeypatch.setattr(launch, "POLL_INTERVAL", 0.01)
    result = launch.launch_detached("/repo", 7332, None)
    assert result.startswith("started (port not open after")


def test_main_already_running_does_not_spawn(monkeypatch, tmp_path, capsys):
    s = _listening_socket()
    try:
        port = s.getsockname()[1]

        def _boom(*a, **k):
            raise AssertionError("Popen must not be called when the port is already open")
        monkeypatch.setattr(launch.subprocess, "Popen", _boom)

        rc = launch.main([str(tmp_path), "--port", str(port)])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "already-running"
    finally:
        s.close()


def test_main_foreground_runs_server_in_foreground(monkeypatch, tmp_path):
    # find_memory_scripts would otherwise pick up this real repo's actual
    # skills/agentqa-write-test/scripts (it exists on disk) regardless of the
    # tmp_path "repo" argument, since that candidate is checked first and
    # doesn't depend on `repo` at all -- stub it so this test's expected argv
    # doesn't depend on incidental repo state.
    monkeypatch.setattr(launch, "find_memory_scripts", lambda repo, studio_root=launch.STUDIO_ROOT: None)
    captured = {}

    class FakeCompleted:
        returncode = 42

    def fake_run(argv, env=None):
        captured["argv"] = argv
        return FakeCompleted()

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    rc = launch.main([str(tmp_path), "--port", "7332", "--foreground"])
    assert rc == 42
    assert captured["argv"] == [sys.executable, "-m", "studio.server",
                                 "--repo", str(tmp_path), "--port", "7332", "--open"]


def test_main_port_defaults_to_env_var(monkeypatch, tmp_path):
    monkeypatch.setattr(launch, "find_memory_scripts", lambda repo, studio_root=launch.STUDIO_ROOT: None)
    monkeypatch.setenv("AGENTQA_STUDIO_PORT", "9999")
    captured = {}

    def fake_run(argv, env=None):
        captured["argv"] = argv

        class FakeCompleted:
            returncode = 0
        return FakeCompleted()

    monkeypatch.setattr(launch.subprocess, "run", fake_run)
    launch.main([str(tmp_path), "--foreground"])
    assert "9999" in captured["argv"]
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py -v`
Expected: `AttributeError` — `_popen_kwargs`, `launch_detached`, and `main` don't exist yet.

- [ ] **Step 7: Implement the CLI**

Append to `skills/agentqa-studio/scripts/studio-launch.py`:

```python
def _popen_kwargs(log_file):
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=log_file, stderr=log_file, env=_env())
    if sys.platform == "win32":
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP | _DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return kwargs


def launch_detached(repo, port, memory_scripts):
    log_path = Path(tempfile.gettempdir()) / "agentqa-studio.log"
    with open(log_path, "ab") as log_file:
        subprocess.Popen(server_argv(repo, port, memory_scripts), **_popen_kwargs(log_file))
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        if port_open(port):
            return "started"
        time.sleep(POLL_INTERVAL)
    return "started (port not open after %.1fs -- see log at %s)" % (POLL_TIMEOUT, log_path)


def run_foreground(repo, port, memory_scripts):
    return subprocess.run(server_argv(repo, port, memory_scripts), env=_env()).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-launch.py")
    ap.add_argument("repo")
    ap.add_argument("--port", type=int,
                     default=int(os.environ.get("AGENTQA_STUDIO_PORT", DEFAULT_PORT)))
    ap.add_argument("--memory-scripts", dest="memory_scripts", default=None)
    ap.add_argument("--foreground", action="store_true")
    args = ap.parse_args(argv)

    memory_scripts = Path(args.memory_scripts) if args.memory_scripts \
        else find_memory_scripts(args.repo)

    if args.foreground:
        return run_foreground(args.repo, args.port, memory_scripts)

    if port_open(args.port):
        print("already-running")
        return 0
    print(launch_detached(args.repo, args.port, memory_scripts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py -v`
Expected: all 15 tests PASS.

- [ ] **Step 9: Make the script executable and commit**

```bash
chmod +x skills/agentqa-studio/scripts/studio-launch.py
git add skills/agentqa-studio/scripts/studio-launch.py skills/agentqa-studio/tests/test_studio_launch.py
git commit -m "feat(studio): add a cross-platform launcher script for the dashboard daemon"
```

---

### Task 2: Wire `studio-launch.py` into SKILL.md, fix the troubleshooting doc

**Files:**
- Modify: `skills/agentqa-studio/SKILL.md:80-88`
- Modify: `skills/agentqa-studio/references/troubleshooting.md:36-40`

**Interfaces:**
- Consumes: `studio-launch.py`'s CLI contract from Task 1 (`python3 scripts/studio-launch.py "$REPO"`, best-effort, exits 0, prints one status line).
- Produces: nothing further downstream — this task only changes agent-facing instructions/docs, not code.

- [ ] **Step 1: Replace the bash-only boot snippet in SKILL.md**

In `skills/agentqa-studio/SKILL.md`, find:

```bash
# App repos need not be git repos — fall back to cwd, exactly like the launcher does.
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! nc -z 127.0.0.1 7332 2>/dev/null; then
  agentqa-studio >/tmp/agentqa-studio.log 2>&1 &   # M1 launcher; self-resolves the repo + opens a browser
fi
CONNECTOR="$(python3 scripts/studio-attach.py "$REPO")"
echo "connector: $CONNECTOR"
```

Replace it with:

```bash
# App repos need not be git repos — fall back to cwd, exactly like the launcher does.
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
python3 scripts/studio-launch.py "$REPO"   # best-effort; starts the daemon detached, opens a browser
CONNECTOR="$(python3 scripts/studio-attach.py "$REPO")"
echo "connector: $CONNECTOR"
```

This is the fix: two flat `python3 script.py arg` lines and one plain variable
assignment, with no `if`, `&&`, `&`, or `nc` — the shape proven to translate
correctly into PowerShell/cmd.exe as well as bash.

- [ ] **Step 2: Fix the stale log-path reference in troubleshooting.md**

In `skills/agentqa-studio/references/troubleshooting.md`, find:

```markdown
## The viewer never came up

Booting the daemon is best-effort and the mailbox files are the source of truth, so
the job still runs. Never abort a run because the daemon failed to start. The
launcher log is at `/tmp/agentqa-studio.log`.
```

Replace it with:

```markdown
## The viewer never came up

Booting the daemon is best-effort and the mailbox files are the source of truth, so
the job still runs. Never abort a run because the daemon failed to start.
`studio-launch.py` prints where it wrote the launcher log (a temp-dir path,
platform-dependent) in its status line — check there.
```

- [ ] **Step 3: Verify the old bash-only pattern is gone**

Run: `grep -n "nc -z\|agentqa-studio >/tmp" skills/agentqa-studio/SKILL.md skills/agentqa-studio/references/troubleshooting.md`
Expected: no output (no matches).

Run: `grep -n "studio-launch.py" skills/agentqa-studio/SKILL.md`
Expected: one match, the new boot line.

- [ ] **Step 4: Commit**

```bash
git add skills/agentqa-studio/SKILL.md skills/agentqa-studio/references/troubleshooting.md
git commit -m "fix(studio): boot the dashboard via a single cross-platform command"
```

---

### Task 3: Windows human-invoked launcher + PATH-install docs fix

**Files:**
- Create: `bin/agentqa-studio.cmd`
- Test: `skills/agentqa-studio/tests/test_studio_launch.py` (append)
- Modify: `docs/agentqa-studio.md:148-149`

**Interfaces:**
- Consumes: `studio-launch.py --foreground` from Task 1.
- Produces: nothing further downstream — this is the last task.

- [ ] **Step 1: Write the failing test for the new shim file**

Append to `skills/agentqa-studio/tests/test_studio_launch.py`:

```python
def test_windows_cmd_shim_delegates_to_studio_launch_foreground():
    cmd_path = SCRIPTS.parent.parent.parent / "bin" / "agentqa-studio.cmd"
    text = cmd_path.read_text()
    assert "studio-launch.py" in text
    assert "--foreground" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py::test_windows_cmd_shim_delegates_to_studio_launch_foreground -v`
Expected: FAIL — `bin/agentqa-studio.cmd` does not exist yet.

- [ ] **Step 3: Create the Windows shim**

Create `bin/agentqa-studio.cmd`:

```bat
@echo off
rem agentqa-studio — launch the AgentQA Studio dashboard against the current app repo.
rem
rem Install on PATH: copy or link this file into a folder already on your PATH,
rem e.g. a personal %USERPROFILE%\bin you've added to PATH yourself.
rem
rem Env: AGENTQA_STUDIO_PORT overrides the default port (7332).
rem
rem All real logic (repo/port/memory-scripts resolution, spawning the daemon)
rem lives in studio-launch.py --foreground — this file only locates Python and
rem forwards to it, so nothing is duplicated in batch script.
python "%~dp0..\skills\agentqa-studio\scripts\studio-launch.py" --foreground "%CD%"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest skills/agentqa-studio/tests/test_studio_launch.py::test_windows_cmd_shim_delegates_to_studio_launch_foreground -v`
Expected: PASS.

- [ ] **Step 5: Fix the stale PATH-install claim in docs/agentqa-studio.md**

In `docs/agentqa-studio.md`, find:

```markdown
> The command is installed on your `PATH` by `/agentqa-init setup` (a symlink in
> `~/.local/bin`). Set `AGENTQA_STUDIO_PORT` to use a port other than `7332`.
```

Replace it with:

```markdown
> Nothing installs `agentqa-studio` onto your `PATH` automatically yet — do it once,
> by hand: on macOS/Linux, `ln -sf "$(pwd)/bin/agentqa-studio" ~/.local/bin/agentqa-studio`
> (and make sure `~/.local/bin` is on `PATH`); on Windows, copy or link
> `bin\agentqa-studio.cmd` into a folder already on your `PATH`. Set
> `AGENTQA_STUDIO_PORT` to use a port other than `7332`.
```

- [ ] **Step 6: Run the full studio test suite**

Run: `python3 -m pytest skills/agentqa-studio/tests/ -v`
Expected: all tests PASS, including every test added in Tasks 1 and 3.

- [ ] **Step 7: Commit**

```bash
git add bin/agentqa-studio.cmd skills/agentqa-studio/tests/test_studio_launch.py docs/agentqa-studio.md
git commit -m "feat(studio): add a Windows launcher shim, fix the stale PATH-install docs"
```

---

## Known limitation (carried from the design spec)

Development happens on macOS with no Windows machine available. Task 1's
cross-platform branch selection is verified by mocking `sys.platform` and
`subprocess`; the POSIX detach path is exercised for real. `bin/agentqa-studio.cmd`
(Task 3) only gets a static-content check here — it cannot be run end-to-end on
this machine. Verify on a real Windows box after merge before considering
Windows support fully confirmed.
