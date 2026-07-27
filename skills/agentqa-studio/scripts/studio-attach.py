#!/usr/bin/env python3
"""Attach this session as *the* connector, displacing whatever was there before.

Attaching is a takeover, not an addition. The mailbox is a set of shared files
with no locking, so two live connectors both polling the inbox is not a
supported state — they race for the same job and answer each other's cards.
Every attach therefore:

  1. mints a new connector id (the previous worker is superseded on its next
     mailbox call and stops),
  2. archives the old inbox/outbox under archive/<ts>/ so the browser opens on a
     clean transcript with no orphaned cards to click,
  3. carries any never-claimed job forward into the fresh inbox — an idea typed
     in the dashboard *before* the agent attached is the normal way to start a
     job, not stale state,
  4. tells the browser, in the new transcript, what it cancelled and why,
  5. writes state.json from scratch, so no key of the old session survives.

Prints the new connector id on stdout; pass it to the other scripts as
`--connector` so a displaced worker fails loudly instead of corrupting the
live session.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_common as sc


def cancellation_notices(prev):
    """What the new session must tell the browser about the one it displaced.

    Pure — takes the previous state.json. Nothing was attached means nothing to
    announce; anything else gets one line naming what was lost, because the
    transcript the user was reading is about to be archived out from under them.
    """
    if not prev.get("attached"):
        return []
    status = prev.get("status")
    if status == "running":
        return ["Previous agent session was cancelled — a new connector attached. "
                "The job it was running (%s) has been dropped."
                % (prev.get("current_job_id") or "unknown")]
    if status == "waiting":
        return ["Previous agent session was cancelled — a new connector attached. "
                "The card it was waiting on can no longer be answered."]
    return ["Previous agent session was replaced — a new connector attached."]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="studio-attach.py")
    ap.add_argument("repo")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    sc.ensure_mailbox(repo)

    prev = sc.read_state(repo)
    notices = cancellation_notices(prev)
    cancelled_job = (prev.get("attached") and prev.get("status") in ("running", "waiting")
                     and prev.get("current_job_id"))

    archived = sc.archive_mailbox(repo)
    carried = []
    if archived is not None:
        carried = sc.unconsumed_jobs(
            sc.read_jsonl(archived / "inbox.jsonl"), prev.get("job_cursor"))
        for job in carried:
            sc.append_line(sc.studio_dir(repo) / "inbox.jsonl", job)

    for line in notices:
        sc.post_outbox(repo, sc.record("error", text=line))
    if cancelled_job:
        sc.post_outbox(repo, sc.record(
            "result", status="abandoned",
            summary="Job %s cancelled — a new connector attached." % cancelled_job))
    for job in carried:
        sc.post_outbox(repo, sc.record(
            "progress",
            text="Queued job carried over: %s" % (job.get("flow_idea") or "")))

    connector = sc.new_connector_id()
    sc.reset_state(repo, connector_id=connector, attached=True, status="idle")

    # stdout is the connector id alone so it can be captured; the story goes to
    # stderr, where it shows up in the agent's tool output.
    if archived is not None:
        print("archived previous mailbox to %s" % archived, file=sys.stderr)
    if cancelled_job:
        print("cancelled in-flight job %s" % cancelled_job, file=sys.stderr)
    for job in carried:
        print("carried over queued job %s: %s"
              % (job.get("id"), job.get("flow_idea") or ""), file=sys.stderr)
    print("attached as connector %s" % connector, file=sys.stderr)
    print(connector)
    return 0


if __name__ == "__main__":
    sys.exit(main())
