# AgentQA Studio

A **local web dashboard** for AgentQA. It shows the state of your test rig, runs
the pytest suite with live output, browses the behavioral-memory store — and, when
an agent attaches, lets you **write a test and answer its checkpoints from the
browser** instead of the terminal.

Studio does not replace the `agentqa-write-test` skill; it is a window onto it and
a control panel for it. It runs the **exact same** test-writing flow — only *where
the human answers* changes.

---

## The two halves

Studio splits along one fact: a web server can stay up for hours, but an agent
only *thinks* while a Claude session is attending to it. So Studio is a daemon
**plus** a connector skill, not one or the other.

```
  agentqa-studio  ─►  THE DASHBOARD  (always-on, no AI)
   (CLI daemon)       Serves the web UI. Runs tests, checks the rig, browses
                      memory. Stays up on its own. Never needs an agent.
                              ▲
                              │  a file "mailbox" in .agentqa/studio/
                              ▼
  /agentqa-studio  ─►  THE CONNECTOR  (a live Claude session)
    (skill)            Attaches to the running dashboard, runs the
                       agentqa-write-test flow, and routes its human
                       checkpoints to browser cards. Detaches when done.
```

- **The daemon is "brainless."** It only serves the UI and bridges the browser to
  files. It has no idea whether an agent is attached, and it runs perfectly well
  with none — as a read-only viewer.
- **The connector is independent.** It reads and writes the mailbox files directly.
  It never depends on the daemon being up to do its work: if you run
  `/agentqa-studio` with no dashboard open, the test still gets written — the
  mailbox files just sit there until a dashboard reads them.

They communicate only through plain files (the same "everything is a file" ethos as
the rest of AgentQA), so the agent can attach or detach at any time without
restarting the dashboard.

### The panels

| Panel | Needs an agent? | What it shows |
|---|---|---|
| **Rig** | no | simulator booted · app installed · Appium up · CodeGraph indexed · config summary |
| **Tests** | no | list tests, run the suite or one file, streamed pytest output, failure artifacts |
| **Memory** | no | `flows` / `screens` / `failures` notes, the `--stale` list, `lint` health (read-only) |
| **Agent** | yes | "Write a test for ___", the live transcript + stepper, and the checkpoint cards |

---

## The mailbox (how the two halves talk)

When an agent is attached, the two halves exchange messages through three
append-only files under `.agentqa/studio/` in your app repo — the **Studio
Protocol v1** mailbox:

- `inbox.jsonl` — browser → agent (a `job`, or a `reply` to a question)
- `outbox.jsonl` — agent → browser (`progress`, a `question`, a `result`, an `error`)
- `state.json` — attach/run status + a heartbeat

These are transient, session-scoped scratch files — gitignored, never committed
(the connector writes the `.gitignore` itself). The dashboard tails the outbox to
the browser over SSE; the agent polls the inbox for your answers.

**The checkpoint cards.** The three human checkpoints in the test-writing flow, plus
any device prompts, become cards instead of terminal questions:

| Card | When |
|---|---|
| **Clarify** | every test — confirm what *success*, *failure*, and *blockers* look like (pre-filled from your product docs when available) |
| **Permission / system prompt** | when the app raises one during exploration (Allow / Deny / Dismiss) |
| **Build** | only when `build.policy: human` — "I've built & installed" after you build the app-code changes |
| **Review** | every test — approve or reject the additions-only diff and the generated test |

---

## How to activate

### Prerequisites

Same project setup as `agentqa-write-test`: a repo configured by
`/agentqa-init init` (it has `.agentqa/config.yml` and a scaffolded
`.agentqa/memory/`). For the **viewer** that is all you need. For the **live
test-writing flow** you also need what any write-test run needs — a booted
simulator/emulator and Appium running (see [`toolchain.md`](toolchain.md)).

### Option A — full experience (agent attached)

In a Claude Code session **at your app repo**, run:

```text
/agentqa-studio
```

The connector boots the dashboard if it isn't already up, opens
`http://127.0.0.1:7332/`, and attaches. The **Agent** panel shows "Agent attached —
idle." Then either type the idea in the dashboard's "Write a test for ___" box, or
just tell the agent in chat — both start the same job. Watch progress stream and
answer the cards as they appear. When the test is green the agent waits for the
next job; end the session to detach.

### Option B — viewer only (no agent)

From a terminal **at your app repo**:

```text
agentqa-studio
```

This starts just the daemon and opens the dashboard as a **read-only viewer** — the
rig status, the test runner, and the memory browser. The Agent panel shows "No
agent connected." Useful for watching the rig or running the suite without writing
a new test. `Ctrl-C` stops it.

> The command is installed on your `PATH` by `/agentqa-init setup` (a symlink in
> `~/.local/bin`). Set `AGENTQA_STUDIO_PORT` to use a port other than `7332`.

---

## Using it — a typical run

1. `/agentqa-studio` → the dashboard opens, the agent attaches.
2. Type **"Write a test for logging in with a valid account"** → **Start**.
3. Progress lines stream and the **stepper** advances
   (`map → clarify → explore → identifiers → build → verify → write → green →
   review → capture`).
4. A **Clarify** card appears — confirm success / failure / blockers → **Submit**.
5. If a permission prompt shows up during exploration, an **ask** card asks how to
   handle it.
6. Under `build.policy: human`, a **Build** card waits for you to build & install
   the app-code changes → **"I've built & installed."**
7. A **Review** card shows the additions-only diff and the generated test →
   **Approve** (or **Reject** with a note).
8. A green **result** links the test file. The agent goes back to waiting.

---

## Token cost — Studio vs. the terminal

Studio runs the **identical** `agentqa-write-test` flow, so the bulk of the work —
indexing, exploring the live app, reading code, running pytest — costs the **same**
either way.

What Studio **adds** is the mailbox transport. Every progress update, every
checkpoint question, and every answer is a small shell call that posts to or polls
the mailbox, and those round-trips accumulate in the agent's context. The terminal
flow has none of this: at a checkpoint it simply ends its turn and waits, and the
waiting itself is free.

The baseline overhead is small — a handful of extra calls per session. The part
that can **grow** is human latency: while you think about a card, the agent *polls*
the mailbox and re-blocks (a round-trip every few minutes), whereas the terminal
skill pays nothing to wait. So a Studio run costs somewhat **more** tokens than the
same run in the terminal, most of it proportional to how long the cards sit
unanswered.

**Rule of thumb:** reach for terminal `/agentqa-write-test` when you're optimizing
token spend or working solo; reach for Studio when the visibility (watch the rig,
the streamed run, the transcript) and the click-to-answer UX are worth the
overhead — e.g. demoing, onboarding, or answering checkpoints without reading a
wall of terminal output.

---

## Notes

- **The mailbox is never committed** — `.agentqa/studio/` is gitignored by the
  connector, and both the daemon and the agent enforce it.
- **The connector never modifies `agentqa-write-test`.** It is a thin transport
  adapter; the flow, its memory, and its green loop are exactly the terminal ones.
- **"No agent connected"** in the Agent panel just means no `/agentqa-studio`
  session is attached — run it in Claude Code at the repo.
- **Design deep-dive:** the architecture, the protocol, and the reasoning are in
  [`docs/superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md`](superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md).
