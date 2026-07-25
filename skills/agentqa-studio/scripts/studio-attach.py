#!/usr/bin/env python3
"""Attach the connector: ensure the mailbox dir + gitignore, init state.json."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def ensure_gitignore(repo):
    d = sc.studio_dir(repo)
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.is_file():
        gi.write_text("*\n", encoding="utf-8")   # ignore the whole transient mailbox


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-attach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    ensure_gitignore(repo)
    sc.write_state(repo, attached=True, status="idle",
                   current_job_id=None, awaiting=None)
    print("attached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
