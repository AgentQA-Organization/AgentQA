# AgentQA Studio — connector lifecycle (and two conversation-panel bugs)

**Date:** 2026-07-27
**Status:** implemented

Three defects, one theme: Studio had no notion of a *session*. The mailbox
outlived the agent that wrote it, so a second `/agentqa-studio` inherited the
first one's wreckage; and the conversation panel painted whatever the mailbox
said without checking that it could be read or answered.

The brainless-daemon / independent-worker split and Studio Protocol v1 are
unchanged. What is added is an identity for "the attached connector" and a
takeover procedure around it.

---

## 1. Conversation panel could not scroll

**Symptom.** With a few cards in the transcript, the panel showed a card cut off
mid-form and nothing would scroll to reveal the rest.

**Root cause.** `.convo` is `display: flex; flex-direction: column` with a capped
height. Its entries were plain flex items, so they kept the default
`flex-shrink: 1`; `.msg-card` sets `overflow: hidden`, which zeroes a flex item's
automatic minimum size. The box therefore *squeezed its children to fit* instead
of overflowing: measured in headless Chrome, a card whose natural height was
414px rendered at 208px, and `scrollHeight == clientHeight == 500` — there was
nothing to scroll and the clipped content was unreachable by any means.

**Fix.** `.convo > * { flex: 0 0 auto; }`. Entries keep their natural height, the
box overflows, `overflow-y: auto` does its job. The cap is now
`min(500px, 60vh)` so a short screen never hides the box's own scrollbar, and
`overscroll-behavior: contain` keeps a scroll that reaches the end from
continuing into the page.

**Sticky-bottom behaviour.** `logAppend` used to force `scrollTop = scrollHeight`
on every record, which — once scrolling worked — would yank a reader out of
history on each progress line. It now measures `isAtBottom(...)` *before*
appending and only follows if the reader was already at the end; otherwise a
"↓ New messages" pill appears, and scrolling back down dismisses it. Trimming
past the 500-entry cap compensates `scrollTop` by the removed height so history
does not slide under the reader.

## 2. Choice options rendered as `[object Object]`

**Root cause.** `renderForm` assumed `q.options[]` were strings: `esc(opt)` on an
object yields `String(obj)`, and `seg.dataset.value = opt` stringifies the same
way. So the button read `[object Object]` **and replied with that literal
string** — the answer the agent received was junk even if the user clicked
correctly. The protocol was the real gap: `protocol_v1.json` only ever showed
string options, so `{label, value}` pairs were a reasonable thing for an agent to
emit and nothing rejected them.

**Fix.** Both shapes are now the contract, documented in the fixture and in
SKILL.md: a bare string (label == value) or `{label, value}`. `optionLabel()` /
`optionValue()` resolve them; the button shows the label, the reply carries the
value.

**Defence in depth.** Every string the UI paints goes through a new `text()`
helper (`esc()` is built on it) that renders objects as compact JSON rather than
`[object Object]`. A malformed field is then visibly wrong and names itself,
instead of hiding behind a placeholder. The remaining interpolations that carry
mailbox or server data — config summary, note bodies, error messages, stale/lint
output — were routed through it too.

---

## 3. Attaching does not displace the previous session

**Symptom.** Running `/agentqa-studio` again left the old session's `state.json`
in place, so the dashboard answered every new idea with `409 a job is already
running`, the transcript still offered cards from an agent that was gone, and two
workers could poll the same inbox.

### Connector identity

`state.json` gains `connector_id`. Every `studio-attach.py` mints a new one; a
worker holding an older id is **superseded** and must stop touching the mailbox.
`--connector <id>` is accepted by wait / post / detach and enforced centrally in
`studio_common.check_connector`. Omitting it keeps the previous unconditional
behaviour, so nothing breaks mid-flow on an upgrade.

Two things make the guard reliable rather than advisory:

- `studio-wait.py` re-checks **every poll**, not just at startup. The common
  collision is a second `/agentqa-studio` starting while a wait is blocked for
  eight minutes.
- The check is load-bearing specifically on `--reply-to`, which writes no state:
  without it a displaced worker would read the answer the user gave the *new*
  session's card and act on it. (Verified by mutation: disabling the check fails
  exactly that test.)

### The takeover, in order

1. Read the previous `state.json` and decide what to announce.
2. `os.replace` inbox + outbox into `archive/<ts>/`. The rename is atomic and
   happens *before* anything reads them, so a record written by a straggler
   either lands in the file we then archive, or in the fresh one — never in a
   gap.
3. Carry never-claimed jobs forward. Everything after `job_cursor` was only ever
   queued; a cursor absent from the archived inbox means nothing there was
   claimed, so it all carries. `job_cursor` resets to `None` — required, since
   the old cursor id no longer exists in the fresh inbox and `_find_job` would
   never get past it.
4. Post the cancellation to the *new* outbox: an `error` line naming what was
   lost, plus a `result: abandoned` when a job was in flight so the browser's
   stepper is released.
5. `reset_state()` — write `state.json` from scratch rather than merging, so no
   key of the old session (a dangling `awaiting`, a `current_job_id` for a job
   nobody is running) survives to wedge the daemon.

### Why a queued job survives a "clean" reset

A job typed into the dashboard *before* the agent attached is the ordinary way to
start work, and picking it up is a documented feature. It is live intent, not
stale state, so it carries forward; the browser is told it did.

### The rotation race the browser would have lost

`tail_outbox` follows the outbox by line offset. When attach rotates the file,
those offsets describe a file that no longer exists: the tail would sit silent
until the fresh file grew past the old one's length, silently swallowing the new
session's first records.

`tail_outbox` now detects a shrinking file, restarts at zero, and yields an
`OUTBOX_RESET` sentinel that the daemon renders as an SSE `event: session`. The
browser clears its transcript on that event.

Doing it on the stream rather than by polling `connector_id` is what makes it
correct: the marker is *ordered before* the new session's records on the same
connection. A 4-second poll would have fired after those records had already
been painted and wiped them.

### Races considered

| race | outcome |
|---|---|
| two attaches in the same second | archive dirs get a `-N` suffix; last writer owns `state.json`; the loser's worker is superseded on its next call |
| attach while a wait is blocked | wait notices within one poll and prints `superseded` |
| attach between a worker's check and its write | `write_state` raises `Superseded`, caught, reported as `superseded` |
| attach while the browser POSTs a job | rename is atomic; the record lands in the archived file (read at step 3, carried forward) or the fresh one |
| attach with an SSE stream open | `OUTBOX_RESET` ahead of the new records |
| a displaced agent detaching at end of turn | `--connector` guard makes it a no-op, so the live session stays attached |

---

## Testing

- `studio/tests/test_convo_render.py` — `text`/`esc`/`optionLabel`/`optionValue`/
  `isAtBottom` sliced out of the shipped `app.js` and run under node, plus a
  guard on the `.convo > *` CSS rule.
- `skills/agentqa-studio/tests/test_studio_lifecycle.py` — 28 tests over attach,
  archive, carry-forward, cancellation notices, and the supersede guards,
  including a threaded test where the takeover lands mid-wait.
- `studio/tests/test_mailbox.py` / `test_server.py` — rotation restart and the
  ordering of `event: session` ahead of the new records.
- Verified against the real daemon in headless Chrome over CDP: layout metrics
  before/after, the four scroll behaviours, and a re-attach with the dashboard
  open (transcript resets to the cancellation note; a job that was refused with
  409 is accepted afterwards).
