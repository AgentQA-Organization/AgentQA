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


def resolve_repo(repo):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True)
    except Exception:
        return str(repo)
    if result.returncode == 0:
        return result.stdout.strip()
    return str(repo)


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
    try:
        return subprocess.run(server_argv(repo, port, memory_scripts), env=_env()).returncode
    except KeyboardInterrupt:
        return 130


def _default_port():
    raw = os.environ.get("AGENTQA_STUDIO_PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-launch.py")
    ap.add_argument("repo")
    ap.add_argument("--port", type=int, default=_default_port())
    ap.add_argument("--memory-scripts", dest="memory_scripts", default=None)
    ap.add_argument("--foreground", action="store_true")
    args = ap.parse_args(argv)
    args.repo = resolve_repo(args.repo)

    if args.foreground:
        memory_scripts = Path(args.memory_scripts) if args.memory_scripts \
            else find_memory_scripts(args.repo)
        return run_foreground(args.repo, args.port, memory_scripts)

    try:
        memory_scripts = Path(args.memory_scripts) if args.memory_scripts \
            else find_memory_scripts(args.repo)
        if port_open(args.port):
            print("already-running")
        else:
            print(launch_detached(args.repo, args.port, memory_scripts))
    except Exception as exc:
        print("not-started (%s)" % exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
