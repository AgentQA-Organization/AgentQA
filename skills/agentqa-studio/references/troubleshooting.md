# Studio troubleshooting

Read this when the dashboard is in a state that doesn't match what you expect.
The normal loop never needs it.

## The dashboard has been sitting at *queued*

A job posted while no agent was watching is **not lost**. It was never claimed, so
`studio-attach.py` carries it into the fresh inbox and your step-2 wait returns it
immediately. Attach and wait — the job runs.

This is the failure mode the same-turn rule in step 1 exists to prevent: attaching
only writes `state.json`, and the only thing that ever consumes a job is
`studio-wait.py` running inside a live turn.

## A job that vanished mid-flight

If the dashboard was showing a job in flight and the transcript is suddenly a short
"previous session was cancelled" note, somebody re-ran `/agentqa-studio` — that
attach cancelled the run. The old transcript is under `.agentqa/studio/archive/`;
the flow itself has to be started again.

## What attach throws away, and what it keeps

Attach leaves Studio clean on purpose: any earlier session is cancelled, its
mailbox archived under `.agentqa/studio/archive/<ts>/`, its `state.json` replaced.

Two things it does **not** throw away:

- a job that was queued but never started — it carries forward into the new inbox
- the archived transcript itself

Attach's stderr names whatever it cancelled or carried over. If it cancelled a job,
tell the user in one line so a disappearing run is never a mystery.

## The viewer never came up

Booting the daemon is best-effort and the mailbox files are the source of truth, so
the job still runs. Never abort a run because the daemon failed to start.
`studio-launch.py` prints where it wrote the launcher log (a temp-dir path,
platform-dependent) in its status line — check there.

## Design rationale

The brainless-daemon / independent-worker boundary, the protocol, and the
pause-point mapping are argued in
[the M2 design spec](../../../docs/superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md).
Read it if a decision in SKILL.md seems arbitrary.
