# AgentQA Studio: cross-platform (Windows) launcher — design

**Date:** 2026-07-28
**Status:** Approved for planning

## Problem

`/agentqa-studio` cannot boot its dashboard daemon on native Windows (PowerShell /
cmd.exe, no WSL/Git Bash on `PATH`). A user session on Windows (via Codex, but the
same applies to any agent host that shells out to PowerShell/cmd.exe natively)
showed:

- `Get-Command agentqa-studio` → not found (`viewer-launcher-not-found`)
- `Test-NetConnection 127.0.0.1 -Port 7332` → closed
- `studio-attach.py` and `studio-wait.py` still succeeded (they only touch mailbox
  files under `.agentqa/studio/`, no HTTP involved), which masked the daemon
  failure — the agent kept going, attached a connector, and sat waiting on a
  mailbox with no dashboard for the human to submit a job through.

## Root cause

`bin/agentqa-studio` — the only thing that starts `studio/server.py` (the
stdlib `http.server` daemon that binds `127.0.0.1:<port>` and serves the
dashboard) — is a bash script (`#!/usr/bin/env bash`) with no Windows-native
counterpart. `skills/agentqa-studio/SKILL.md` step 1's boot instructions are
themselves POSIX-only (`nc -z`, `&` backgrounding, a hardcoded `/tmp/...log`
path), independent of the launcher binary issue.

Confirmed by grep across the whole repo: there is **zero** mention of
"Windows" or "WSL" anywhere in `studio/`, `skills/`, `bin/`, or `docs/`. This
is unimplemented, not a regression.

A second, smaller finding: `docs/agentqa-studio.md` claims `agentqa-studio` is
"installed on your PATH by `/agentqa-init setup`" — no script anywhere
actually does this, on any OS. That line is stale/aspirational; installing the
launcher onto `PATH` has always been a manual step (per the comment header in
`bin/agentqa-studio` itself).

## Evidence for the fix direction

In the same Windows transcript, `python3 scripts/studio-attach.py "$REPO"`
(bash-flavored pseudocode in SKILL.md) was correctly translated by the agent
into working PowerShell and ran successfully. The boot line — containing
`if`/`nc -z`/`&` — was not translated successfully. The pattern: **a flat
`python3 <script> [args]` command line, with no shell control-flow, piping, or
backgrounding syntax, translates reliably across bash/PowerShell/cmd.exe; a
command embedding shell-specific syntax does not.**

## Scope

**In scope:**
- The agent boots the dashboard daemon reliably from native Windows
  (PowerShell/cmd.exe), with no behavior change on POSIX.
- A human can also start the dashboard directly from a Windows shell (parity
  with `bin/agentqa-studio` on POSIX), once manually placed on `PATH`.
- Fix the stale PATH-install doc claim, for both platforms.

**Out of scope:**
- Making the rest of `/agentqa-init setup` (Appium, XCUITest/UiAutomator2
  driver install, Android SDK, Python venv, agent-device, CodeGraph) run
  natively on Windows. That toolchain is validated against macOS + iOS
  simulator and is a much larger, separate effort — iOS automation in
  particular can never run on Windows at all.
- Automating `PATH` mutation on Windows (`setx` or registry edits). Hard to
  reverse and easy to corrupt an existing `PATH`; the fix prints instructions,
  the user applies them, matching the existing POSIX convention (also
  manual).
- Refactoring `bin/agentqa-studio` (POSIX). It works and is tested; left
  untouched.

## Design

### 1. `skills/agentqa-studio/scripts/studio-launch.py` (new)

Owns all "boot the daemon if it isn't up" logic, replacing the bash snippet
in SKILL.md step 1. Pure stdlib (`socket`, `subprocess`, `sys`, `pathlib`,
`tempfile`, `time`) — no new dependencies.

```
studio-launch.py <repo> [--port N] [--memory-scripts PATH] [--foreground]
```

- **Interpreter**: uses `sys.executable` (the interpreter already running
  this script) to spawn `-m studio.server`, instead of searching `PATH` for
  `python3` — sidesteps Windows systems that only have `python`, not
  `python3`.
- **Default mode** (what SKILL.md step 1 calls): checks `127.0.0.1:<port>` via
  `socket` (cross-platform). If already open, prints `already-running` and
  exits 0. Otherwise spawns `python -m studio.server --repo <repo> --port
  <port> --open [--memory-scripts <path>]` as a **detached** background
  process:
  - POSIX: `subprocess.Popen(..., start_new_session=True)`
  - Windows: `subprocess.Popen(..., creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)`
  - stdout/stderr redirected to a log file under `tempfile.gettempdir()`
    (not a hardcoded `/tmp` path).
  - Polls the port for up to ~2s afterward so the status line is honest:
    prints `started` if the port came up, or `started (port not open after
    2s — see log at <path>)` if not.
  - **Always exits 0.** Booting is best-effort per SKILL.md's existing
    mandate ("never abort a run because the daemon failed to start") — this
    script must never be the reason a job aborts.
- **`--foreground`**: does not detach; runs `studio.server` as a direct child
  and blocks until it exits (Ctrl-C forwarded), returning its exit code. Used
  by the Windows human-invoked shim (below) so no process-launch logic is
  duplicated in batch script.
- **`MEM_SCRIPTS` auto-detection**: same candidate search `bin/agentqa-studio`
  already does (`STUDIO_ROOT/skills/agentqa-write-test/scripts`,
  `~/.claude/skills/agentqa-write-test/scripts`,
  `<repo>/.claude/skills/agentqa-write-test/scripts`), ported to Python.

### 2. `skills/agentqa-studio/SKILL.md` step 1

Replace:
```bash
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! nc -z 127.0.0.1 7332 2>/dev/null; then
  agentqa-studio >/tmp/agentqa-studio.log 2>&1 &   # M1 launcher; self-resolves the repo + opens a browser
fi
CONNECTOR="$(python3 scripts/studio-attach.py "$REPO")"
echo "connector: $CONNECTOR"
```
with:
```bash
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
python3 scripts/studio-launch.py "$REPO"   # best-effort; starts the daemon detached, opens a browser
CONNECTOR="$(python3 scripts/studio-attach.py "$REPO")"
echo "connector: $CONNECTOR"
```
Two flat `python3 script.py arg` lines plus one plain variable assignment —
no `if`, `&&`, `&`, or `nc`. Update
`skills/agentqa-studio/references/troubleshooting.md`'s "The viewer never
came up" section to say the log path is whatever `studio-launch.py` printed,
rather than hardcoding `/tmp/agentqa-studio.log`.

### 3. `bin/agentqa-studio.cmd` (new)

Thin Windows shim for a human to run directly, once it's on `PATH` — parity
with `bin/agentqa-studio` on POSIX, but delegates all real logic to the
already-tested Python script rather than reimplementing repo/port/mem-scripts
resolution in batch:

```bat
@echo off
python "%~dp0..\skills\agentqa-studio\scripts\studio-launch.py" --foreground "%CD%"
```

`bin/agentqa-studio` (bash) is left unchanged.

### 4. Docs: `docs/agentqa-studio.md`

Replace the stale "installed on your `PATH` by `/agentqa-init setup`" line
with accurate manual install steps for **both** platforms: symlink
`bin/agentqa-studio` into `~/.local/bin` (existing POSIX convention,
unchanged) or copy/link `bin\agentqa-studio.cmd` into a folder already on
`PATH` (Windows), with a one-time "add this folder to `PATH`" note the user
applies themselves — no automated `PATH`/registry edits.

## Testing strategy & known limitation

New tests in `skills/agentqa-studio/tests/` for `studio-launch.py`:
- port-check logic (bind a real local socket, confirm detection)
- `MEM_SCRIPTS` candidate search
- idempotency (already-open port → no second spawn)
- platform branch selection: mock `sys.platform` and assert the right
  `Popen` kwargs (`start_new_session` vs `creationflags`) are chosen, without
  actually needing to run on Windows
- `--foreground` argv assembly

**Known limitation**: development happens on macOS with no Windows machine
available. The POSIX detach path and all platform-selection logic get real
or mocked test coverage; `bin/agentqa-studio.cmd` and the Windows detach path
cannot be exercised end-to-end here. This should be verified on a real
Windows machine after merge before considering Windows support fully
confirmed.
