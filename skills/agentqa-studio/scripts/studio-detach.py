#!/usr/bin/env python3
"""Detach the connector: mark state detached/idle.

Pass `--connector <id>` so a session that has already been displaced leaves the
live one alone. Without it, an old agent tidying up at the end of its turn would
flip `attached` to false under the connector that replaced it, and the dashboard
would read "No agent connected" while an agent is in fact working.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-detach.py")
    ap.add_argument("repo")
    ap.add_argument("--connector", default=None,
                    help="this session's connector id (from studio-attach.py)")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    try:
        sc.write_state(repo, connector=args.connector,
                       attached=False, status="idle", awaiting=None)
    except sc.Superseded as taken_over:
        # Not an error: this session was already replaced, so there is nothing
        # of ours left to detach.
        print("already superseded by connector %s — leaving state alone" % taken_over)
        return 0
    print("detached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
