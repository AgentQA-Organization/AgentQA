#!/usr/bin/env python3
"""Post a Studio Protocol record to the outbox (agent -> browser), update state.

  studio-post.py <repo> progress --text "..." [--stage map]
  studio-post.py <repo> question --kind form   --subtype clarify --prompt "..." --questions '<json array>'
  studio-post.py <repo> question --kind confirm --subtype build  --prompt "..."
  studio-post.py <repo> question --kind review --subtype review  --prompt "..." --diff "<text>" --test-files '<json array>'
  studio-post.py <repo> result   --status green --summary "..." [--test-path ...]
  studio-post.py <repo> error    --text "..."

Prints the record id. A `question` flips state to waiting/awaiting:<id>; a
`result` flips state back to idle; anything else just bumps the heartbeat.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-post.py")
    ap.add_argument("repo")
    sub = ap.add_subparsers(dest="type", required=True)

    p = sub.add_parser("progress")
    p.add_argument("--text", required=True)
    p.add_argument("--stage", default=None)

    q = sub.add_parser("question")
    q.add_argument("--kind", required=True, choices=["form", "confirm", "review"])
    q.add_argument("--subtype", required=True,
                   choices=["clarify", "ask", "build", "review"])
    q.add_argument("--prompt", required=True)
    q.add_argument("--questions", default=None, help="JSON array for form questions")
    q.add_argument("--diff", default=None)
    q.add_argument("--test-files", default=None, help="JSON array of {path,content}")

    r = sub.add_parser("result")
    r.add_argument("--status", required=True, choices=["green", "abandoned"])
    r.add_argument("--summary", default="")
    r.add_argument("--test-path", default=None)

    e = sub.add_parser("error")
    e.add_argument("--text", required=True)

    args = ap.parse_args(argv)
    repo = Path(args.repo)

    if args.type == "progress":
        payload = {"text": args.text}
        if args.stage:
            payload["stage"] = args.stage
        rec = sc.record("progress", **payload)
    elif args.type == "question":
        payload = {"kind": args.kind, "subtype": args.subtype, "prompt": args.prompt}
        if args.questions:
            payload["questions"] = json.loads(args.questions)
        if args.diff is not None:
            payload["diff"] = args.diff
        if args.test_files:
            payload["test_files"] = json.loads(args.test_files)
        rec = sc.record("question", **payload)
    elif args.type == "result":
        payload = {"status": args.status, "summary": args.summary}
        if args.test_path:
            payload["test_path"] = args.test_path
        rec = sc.record("result", **payload)
    else:  # error
        rec = sc.record("error", text=args.text)

    sc.post_outbox(repo, rec)
    if args.type == "question":
        sc.write_state(repo, status="waiting", awaiting=rec["id"])
    elif args.type == "result":
        sc.write_state(repo, status="idle", awaiting=None)
    else:
        sc.write_state(repo)  # heartbeat bump
    print(rec["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
