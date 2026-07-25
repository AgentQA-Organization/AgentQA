#!/usr/bin/env python3
"""Detach the connector: mark state detached/idle."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-detach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    sc.write_state(Path(args.repo), attached=False, status="idle", awaiting=None)
    print("detached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
