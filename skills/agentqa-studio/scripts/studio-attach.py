#!/usr/bin/env python3
"""Attach the connector: ensure the mailbox dir + gitignore, init state.json."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-attach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    sc.ensure_mailbox(repo)
    sc.write_state(repo, attached=True, status="idle",
                   current_job_id=None, awaiting=None)
    print("attached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
