#!/usr/bin/env python3
"""Block-poll the inbox for the next job or a reply, keeping the heartbeat warm.

  studio-wait.py <repo> --job                 # next unprocessed job (respects job_cursor)
  studio-wait.py <repo> --reply-to <qid>      # the reply to a question

Prints exactly one JSON object:
  {"status":"answered","record":{...}}    the awaited job/reply arrived
  {"status":"waiting"}                     timed out under the tool cap — the caller
                                           simply runs it again to re-block

Exit is 0 for both (waiting is not an error). A nonzero exit means the script
itself failed, matching the house convention (0 = ok, nonzero = failure).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc

DEFAULT_TIMEOUT = 480.0   # ~8 min, safely under a 600s tool cap
DEFAULT_POLL = 1.0


def _find_job(repo):
    cursor = sc.read_state(repo).get("job_cursor")
    passed = cursor is None
    for rec in sc.read_inbox(repo):
        if rec.get("type") != "job":
            continue
        if passed:
            return rec
        if rec.get("id") == cursor:
            passed = True
    return None


def _find_reply(repo, qid):
    for rec in sc.read_inbox(repo):
        if rec.get("type") == "reply" and rec.get("reply_to") == qid:
            return rec
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-wait.py")
    ap.add_argument("repo")
    ap.add_argument("--job", action="store_true")
    ap.add_argument("--reply-to", dest="reply_to", default=None)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument("--poll", type=float, default=DEFAULT_POLL)
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    if not args.job and not args.reply_to:
        ap.error("one of --job or --reply-to is required")

    deadline = time.time() + args.timeout
    while True:
        rec = _find_job(repo) if args.job else _find_reply(repo, args.reply_to)
        if rec is not None:
            if args.job:
                sc.write_state(repo, status="running",
                               current_job_id=rec["id"], job_cursor=rec["id"])
            print(json.dumps({"status": "answered", "record": rec}))
            return 0
        if time.time() >= deadline:
            print(json.dumps({"status": "waiting"}))
            return 0
        sc.write_state(repo)          # heartbeat bump while we wait
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
