# AgentQA Studio — M2 (Agent Bridge) design

**Date:** 2026-07-25
**Status:** Approved (design) — implementation plan pending
**Builds on:** [M1 dashboard design](2026-07-24-agentqa-studio-dashboard-design.md) ·
[M1 implementation plan](../plans/2026-07-24-agentqa-studio-m1-dashboard.md)

## Where M1 left off

M1 shipped the always-on half of AgentQA Studio: the `agentqa-studio` daemon
(config / rig / runner / memory_view / server) and a vanilla-JS UI with three
panels — rig status, test runner (streamed pytest over SSE), and memory browser —
plus the `bin/agentqa-studio` launcher on PATH. It is useful with **no agent
attached**: see the rig, run tests, browse what the agent has learned.

M2 adds the other half — the **agent bridge** — so the whole
`agentqa-write-test` flow can be driven from the browser: the "Write a test
for ___" box, the live agent transcript, and the three human-in-the-loop
checkpoints as browser cards instead of terminal prompts.

## Core principle — the boundary

M2 has exactly one hard architectural rule, and every later decision derives from
it:

> **The daemon stays brainless. The worker stays independent. They communicate
> only through files, under a versioned protocol.**

- **Brainless daemon (Half A).** The always-on server never reads the agent's
  messages to *act* on them and never writes them. It only bridges the browser to
  the mailbox files: append the browser's messages to the inbox, tail the outbox
  to the browser, read `state.json`. It has no idea whether a brain is attached.
- **Independent worker (Half B).** The `/agentqa-studio` connector — a live Claude
  session — reads and writes the mailbox files **directly** with its native
  tools, never through the daemon.

**Litmus test for the boundary:** run the connector with no daemon up and no
browser ever attached, and it must still produce a green test and write memory —
the mailbox files just sit there unread until a daemon comes up and a browser
tails them. The worker's ability to *work* is never coupled to the viewer being
up. That is why files, not an HTTP API, are the integration point: they outlive
both processes and let the agent attach/detach and the daemon start/stop
independently.

**The one cost, named honestly.** The protocol write-path then exists in **two
implementations** — `studio/mailbox.py` (daemon side) and the connector's helper
scripts (agent side). This is the same dual-reader pattern `.agentqa/config.yml`
already lives with (read by both a bash `sed` reader and `studio/config.py`), and
it is managed the same way: a single pinned schema, with **both sides tested
against one canonical fixture** (see "Protocol as executable spec"). We pay a
small duplication cost to keep the two processes independent; that trade is
deliberate.

**The only scenario that would flip this** is the worker running on a *different
machine* than the daemon — then shared files break and the worker would have to
speak HTTP. That is the remote / multi-host case, explicitly out of scope. If it
ever became a goal, the connector's helper scripts are exactly the seam you would
swap to talk HTTP instead of touching files — already isolated as the transport
layer.

## The Studio Protocol v1

The mailbox is a **protocol**, not a file format. Message *types* are the
first-class concept; append-only JSONL is the current transport. Because the
browser only ever speaks HTTP/SSE to the daemon, and only `mailbox.py` + the
helper scripts touch the files, the transport could later become SQLite/Redis/etc.
with no change to the browser, the endpoints, or the card logic — the HTTP seam
already provides that insulation, so **no separate backend-abstraction layer is
built** (YAGNI against the "plain files" ethos).

### Transport rules

- Append-only JSONL, one record per line.
- Full-line writes via `O_APPEND` so the daemon process and the agent's shell can
  write from separate processes safely; a reader ignores a partial trailing line
  (no terminating newline yet).
- **Every record carries `v: 1`.** Records are self-describing lines; a stale
  agent talking to a newer daemon fails loudly rather than silently misparsing.
  (`v:1` is preferred over a verbose `"protocol":"studio-v1"` on every line purely
  for log readability — cosmetic.)
- Every record also carries `id` (unique), `ts` (ISO-8601), and `type`.

### Protocol as executable spec

The canonical definition of Protocol v1 is a **golden-record fixture**
(`studio/protocol/v1.json`) enumerating one example of every message shape plus
the `state.json` shape. It is the source of truth, not merely a test asset:

- Both the daemon tests and the connector-script tests load this **same** file and
  assert their encode/parse round-trips it.
- A protocol change *is* an edit to the fixture, which fails both sides' tests
  until each is updated — neither implementation can silently drift from the
  other. This is how the two-implementation cost above is paid down.

### Message catalog

**`inbox.jsonl` — browser → agent** (only two shapes):

| type | payload | meaning |
|---|---|---|
| `job` | `flow_idea: str` | start a write-test job for this idea |
| `reply` | `reply_to: <question-id>` + one of: `answers:{qid:val}` / `decision:"built"` / `decision:"approve"\|"reject", note?` | answer the question with that id |

**`outbox.jsonl` — agent → browser:**

| type | payload | meaning |
|---|---|---|
| `progress` | `text: str`, **`stage?: <slug>`** | live status line; optional coarse phase slug |
| `question` | `kind`, `subtype`, `prompt`, + kind-specific fields | a human decision is needed (see below) |
| `result` | `status:"green"\|"abandoned"`, `summary`, `test_path?` | the job ended |
| `error` | `text: str` | the agent could not proceed |

`question` has three `kind`s:

- **`kind:"form"`** (`subtype:"clarify"` or `"ask"`) —
  `questions:[{qid, label, kind:"text"|"choice", options?, default?}]`. Clarify
  carries the 3–4 requirement questions (entry-point as a `choice` when >1 exists;
  step-0 doc answers become `default`s — preserving write-test's
  "confirm-or-correct, don't ask cold"). `ask` is the ad-hoc step-3 system-view
  prompt, usually a single `choice` field.
- **`kind:"confirm"`** (`subtype:"build"`) — just `prompt`. The build checkpoint.
- **`kind:"review"`** (`subtype:"review"`) — `prompt`, `diff` (additions-only),
  `test_files:[{path, content}]`. The diff is carried **on** the review question
  (it is the only place a diff is shown; there is no separate `diff` message).

`progress.stage` draws from a small controlled vocabulary aligned to write-test's
phases — `map · clarify · explore · identifiers · build · verify · write · green ·
review · capture` — but it is **optional** and uses coarse phase **slugs**, never
hard-coupled step numbers, so it degrades gracefully and stays reusable by any
future skill that adopts the protocol.

### `state.json`

A single small document (not append-only):

```json
{
  "v": 1,
  "attached": true,
  "heartbeat_ts": "2026-07-25T10:00:00Z",
  "status": "idle | running | waiting",
  "current_job_id": null,
  "awaiting": null,
  "job_cursor": null
}
```

- **Correlation is by id.** The browser sees a `question`, renders a card, and on
  submit POSTs a `reply` with `reply_to = question.id`. The agent's blocking wait
  unblocks on the first `reply` whose `reply_to` matches — unambiguous regardless
  of file offset, because ids are unique.
- **`job_cursor`** records the last job the connector has picked up, so old jobs in
  the inbox are never re-run. `awaiting` is the question id currently blocking on a
  human. Both give the "what's pending" answer in O(1) — nothing scans the inbox.

### Single worker in v1 — not foreclosed

`state.json` describes one worker. Multi-worker is out of scope (the write-test
flow drives one simulator with one app install; concurrent heterogeneous workers
would fight over the device). It is not foreclosed: if it ever mattered,
`state.json` becomes keyed by worker id (`{"workers": {"claude": {...}}}`) — a
mechanical change to one file, built only if needed.

## The mailbox files

Three files in the **app-under-test** repo at `.agentqa/studio/`, siblings of
`config.yml` and `memory/`:

- `inbox.jsonl`, `outbox.jsonl` — the protocol streams above.
- `state.json` — current run/attach state.

They are transient, session-scoped scratch — treated like the memory working-layer
files (`.session-requirement.md`, `.run-checkpoint.md`) and never committed.

**Self-contained ignore.** There is no repo-wide `.agentqa/.gitignore`; the
existing ignore is scoped inside `.agentqa/memory/.gitignore` (managed by
`scaffold-memory.sh`). So `studio-attach.py` drops `.agentqa/studio/.gitignore`
= `*` on attach — the same scoped-`.gitignore`-per-subdir pattern the memory
scaffold already uses. **No change to `agentqa-init` or `agentqa-write-test` is
required** — the adapter guarantee holds end to end.

## Server additions (Half A stays brainless)

A new module `studio/mailbox.py` (append a record, read `state.json`, tail a
JSONL file) plus these routes on the existing daemon:

- `GET  /api/studio/state` → `state.json` (defaults to idle/detached if absent).
- `POST /api/studio/job {flow_idea}` → append a `job` to the inbox; **409 if a
  job is already running**.
- `POST /api/studio/reply {reply_to, …}` → append a `reply` to the inbox.
- `GET  /api/studio/stream` → SSE that **tails `outbox.jsonl`** (polls for new
  full lines, pushes each record) — a new SSE source distinct from M1's in-process
  run queue.

The daemon never reads the outbox to act and never writes it. The agent side does
not go through the server at all.

## The connector skill — `/agentqa-studio`

A thin **transport adapter**, built via the **skill-creator** skill (locked
constraint). It runs the **unchanged** `agentqa-write-test` flow and only
redirects that flow's existing human-interaction points from the terminal to the
mailbox. Its own responsibilities are four:

1. **Attach** — best-effort boot the daemon (port check → background-launch the M1
   `agentqa-studio` if it is down, so the human gets a viewer), ensure
   `.agentqa/studio/.gitignore`, init `state.json` (`attached:true, status:idle`).
   *Boot is best-effort: if it fails, the job still runs — the mailbox files are
   written regardless (the litmus test).*
2. **Watch** — block-wait for a `job` on the inbox. On arrival: `status:running`,
   `current_job_id`, advance `job_cursor`.
3. **Delegate** — run `agentqa-write-test` as written for that `flow_idea`. Steps
   0–9, the memory scripts, the green loop: all identical.
4. **Redirect + post-back** — where the flow would stop and ask the terminal, post
   a `question` and block for the matching `reply` instead; emit `progress` at step
   boundaries and `result` at the end; then loop back to Watch, or `detach` when
   the user ends the session.

### The mapping — write-test's pause points → protocol messages

The whole adapter is this table. Write-test already has exactly these pause
points; the connector only changes *where the question goes*.

| write-test pause point | when | out (`outbox`) | in (`inbox`) | widget |
|---|---|---|---|---|
| **Step 2 — clarify** (success / failure / blockers, + entry-point when >1) | every job | `question kind:form subtype:clarify` (doc answers as `default`s) | `reply answers:{qid:val}` | form |
| **Step 3 — system-view ask** (permission / OTP / springboard: allow / deny / dismiss) | 0..N, only when one appears | `question kind:form subtype:ask` (usually one `choice`) | `reply answers:{qid:val}` | form |
| **Step 5 — build checkpoint** (`WAITING_FOR_HUMAN_BUILD`) | **only when `build.policy: human`** — silent under `agent` | `question kind:confirm subtype:build` | `reply decision:"built"` | button |
| **Step 8 — review** (additions-only diff + the test) | every job | `question kind:review subtype:review` (carries `diff` + `test_files`) | `reply decision:"approve"\|"reject", note?` | diff + Approve/Reject |

Everything between these — indexing, exploring with `agent-device`, adding
identifiers, verifying, the green loop — is silent work that emits `progress`
(optionally with a `stage`) and needs no human. On write-test **abandoning** a
run, the connector emits `result status:"abandoned"` (+ `error` with the reason)
and lets write-test's own cleanup delete the working-layer files. A **reject**
reply's `note` is fed back exactly like a terminal rejection — the agent addresses
it and re-presents. The connector **never edits `agentqa-write-test`**: the
redirect is entirely "when the flow says *ask the user*, post a question instead."

### Helper scripts — the testable core

Mechanics live in tested scripts under `skills/agentqa-studio/scripts/`, sharing
`studio_common.py` (protocol constants, `v:1` record builders, `O_APPEND` JSONL
writes, `state.json` read/write — the agent-side half of the contract). This
mirrors the `memory-*` precedent, keeping the skill prose thin.

- **`studio-attach.py`** — ensure the mailbox dir + `.gitignore`; init/refresh
  `state.json` (attached, idle, heartbeat).
- **`studio-wait.py --job` / `--reply-to <qid>`** — block-poll the inbox for the
  next job (respecting `job_cursor`) or the reply matching a question id; **refresh
  `heartbeat_ts` each poll tick**; return the record on stdout when found. It
  signals control flow **in its JSON payload** — `{"status":"answered", ...}` vs
  `{"status":"waiting"}` — and re-blocks under the ~8-min tool cap, so the agent
  re-invokes on a `waiting` result. **Nonzero exit is reserved for genuine script
  failure**, matching the house convention (`0` = ok, nonzero = failure-with-
  message, as in `memory-write.py`) — no special "retry" exit code is invented.
- **`studio-post.py --type progress|question|result|error …`** — build a `v:1`
  record, append to the outbox, and update `state.json` (a `question` sets
  `status:waiting` + `awaiting:<qid>` and returns the qid; `result` sets
  `status:idle`, clears `awaiting`).
- **`studio-detach.py`** — `attached:false, status:idle` on session end.

The skill body then reads: *attach → `wait --job` → post progress → run write-test,
routing each pause through `post question` + `wait --reply-to` → post result → loop
or detach.*

### Liveness

`studio-wait` keeps `heartbeat_ts` warm through the **longest** gaps (a human
thinking at a card). During silent agent work the heartbeat can briefly age; the
browser reads it **status-aware**: `status:running` + stale heartbeat = "working…",
not disconnected — only `status:waiting` with a stale heartbeat means the agent's
turn actually died mid-wait.

## Panel 3 — Agent conversation (UI)

Joins the three M1 panels, full-width below the runner (the review diff needs
horizontal room). Driven entirely by `GET /api/studio/stream` + `GET
/api/studio/state`; all vanilla JS in the existing `app.js`/`style.css`, no
framework, no new server mechanism beyond the file-tail.

- **Attach indicator** — "Agent attached" vs "No agent connected — run
  `/agentqa-studio` in Claude Code", using the status-aware liveness above.
- **Job starter** — "Write a test for ___" → `POST /api/studio/job`. Always
  enabled *unless a job is running* (mirrors the 409); with no agent attached, the
  job posts and shows "queued — waiting for an agent."
- **Conversation log** — append-only, fed by SSE. `progress` renders as a
  timeline; when `stage` is present it also advances a compact **stepper**. The
  stepper derives **solely from `stage` slugs** (never progress text, never
  write-test step numbers): the UI ships a default ordered slug track for the full
  greyed-out view but treats it as a display hint — any slug not in the list still
  renders (arrival order), so a future skill's phases just work. A **bounded-DOM
  soft cap** keeps the last ~500 entries (older ones drop from the DOM; the full
  transcript still lives in the outbox and replays on reconnect; the active card is
  always recent, so never dropped). **No virtualization** (YAGNI; fights the
  no-build constraint).
- **Cards** — a `question` renders its widget inline and becomes the active card:
  - `form` (clarify / ask) — one field per question, text inputs + choice radios,
    `default`s pre-filled → `reply {answers}`.
  - `confirm` (build) — prompt + single **"I've built & installed"** button →
    `reply {decision:"built"}`.
  - `review` — the additions-only `diff` and each `test_file` in their own
    `overflow-x:auto` scroll box (simple +/− line coloring, no syntax-highlight
    dependency), then **Approve / Reject** (reject reveals a note field) → `reply
    {decision, note?}`.
  - On submit the card **locks** to its chosen answer, keeping the log a clean
    transcript.
- **Result** — `result` renders a terminal card (green + `test_path` linking to the
  runner panel, or abandoned); `error` renders inline; the panel returns to idle
  and the starter re-enables.
- **Reconnect** — the SSE tail replays the outbox from the start (or a cursor) on
  connect, so a browser opened mid-job reconstructs the whole transcript and lands
  on the active card. This is the payoff of the outbox being the append-only source
  of truth.

## Scope

**In scope (M2 first cut):**
- `.agentqa/studio/` mailbox (inbox / outbox / state.json) under Studio Protocol v1.
- `studio/mailbox.py` + the four new endpoints (`state`, `job`, `reply`, `stream`).
- `studio/protocol/v1.json` canonical fixture.
- Panel 3 + four card widgets + `stage` stepper.
- `/agentqa-studio` connector skill (via skill-creator) + helper scripts.
- Redirect of write-test's four pause points: clarify, step-3 ask, build (human
  policy only), review.

**Out of scope / deferred** (named so the plan can't creep):
- Standalone `diagnose` job.
- Runner credential-prompt UI (M1's deferred item) — still deferred; the agent flow
  uses the session env like the terminal.
- Multi-worker / multi-project / remote-host; transport-swap abstraction; durable
  job history.
- Editing memory or a test editor in the UI.
- Auto-woken `/loop` agent — attach stays skill-invoked.

## Testing strategy

- `studio/mailbox.py` + endpoints → TDD like M1 (unit + live-server tests
  mirroring `test_server.py`).
- Helper scripts (`studio_common`, attach / wait / post / detach) → TDD like the
  `memory-*` scripts (record shape, state transitions, `wait`'s waiting/answered
  payload, job cursor).
- **Both sides validate against `studio/protocol/v1.json`** — the canonical fixture
  is the single source of truth; a protocol change is a fixture edit that fails
  both sides until updated.
- Connector prose → authored via skill-creator and validated by its verify loop;
  mechanics live in the tested scripts, so the prose stays thin.
- Panel 3 JS → asset-serving smoke test + a manual end-to-end smoke (a real
  write-test job driven through the browser), like M1 Task 6.

## Plan shape (for writing-plans)

Inner-to-outer, so the connector skill is authored against a running server — as
the M1 doc intended ("lets the bridge be designed against a real, running
server"):

1. Protocol fixture + `studio/mailbox.py`.
2. Server endpoints + SSE outbox tail.
3. Helper scripts + `studio_common.py`.
4. Panel 3 UI.
5. Connector skill via skill-creator.
6. End-to-end smoke (a real write-test job through the browser).

## Constraints carried from M1

- Stdlib `http.server` + vanilla JS — **no framework, no npm, no build step**.
- **No new runtime dependencies**; Python **3.9.6** (no 3.10+ syntax).
- Studio port **7332**.
- **Credentials never stored or logged.**
- Command name stays **`agentqa-studio`** (hyphen).
- **No commits or pushes without the user's say-so.**

## Decisions locked

- Mailbox is the **Studio Protocol v1**; JSONL is the current transport; every
  record carries `v:1`.
- The daemon is brainless; the worker is independent; files are the contract. The
  worker never depends on the daemon to do its job.
- `studio/protocol/v1.json` is the canonical, executable spec of the protocol —
  both implementations test against it.
- The connector is a transport adapter: **`agentqa-write-test` is not modified**;
  only its four human-interaction points are redirected to the mailbox.
- Build card appears **only** under `build.policy: human`.
- `studio-wait` signals waiting/answered in its JSON payload; nonzero exit stays
  "genuine failure" per the house convention.
- Single worker in v1, not foreclosed; multi-worker / remote-host out of scope.
- The connector skill is created via **skill-creator**.
