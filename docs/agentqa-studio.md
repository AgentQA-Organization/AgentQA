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
| **System dialog** | when the phone raises a permission prompt, OTP, or springboard pop-up during exploration (Allow / Deny / Dismiss) |
| **Permission** | when Claude Code would otherwise raise a permission dialog in the terminal — approve allows the write; reject denies it (Claude Code's documented behavior for this hook). Your note is meant to reach the agent as the denial reason; whether it actually does hasn't been confirmed yet |
| **Build** | only when `build.policy: human` — "I've built & installed" after you build the app-code changes |
| **Review** | every test — approve or reject the additions-only diff and the generated test |

**Why some writes never ask.** `/agentqa-init init` allowlists `.agentqa/**` and
your `test_dir`, because those are AgentQA's own working area and the step-8
Review card already shows you their diff before anything is kept. Everything else
— app source, or any path outside those two — raises a Permission card. If no
agent is attached to Studio, nothing changes: the prompt appears in the terminal
exactly as before.

**Repo initialised before this allowlist existed?** Re-run
`skills/agentqa-init/scripts/scaffold-permissions.sh` (or just `/agentqa-init init`
again) to add it — it merges into your existing `.claude/settings.json` and is
safe to re-run. Without it, every AgentQA write raises a Permission card, which
is exactly what the allowlist exists to prevent.

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
a new test.

### Stopping it

Click the **power button** in the dashboard's top-right corner, or press `Ctrl-C`
in the terminal that launched it. Both stop the same thing — the daemon.

If a job or a test run is in flight, the confirm dialog names it first, because
stopping the daemon **only stops the browser bridge**:

- **An attached agent keeps running.** The connector reads and writes the mailbox
  files under `.agentqa/studio/` directly, never over HTTP. Stop it in Claude Code.
  Anything it asks you while the dashboard is down has nowhere to be answered.
- **An in-flight `pytest` run keeps running.** It is a child process; stopping the
  daemon just stops watching its output.

> Nothing installs `agentqa-studio` onto your `PATH` automatically yet — do it once,
> by hand: on macOS/Linux, `ln -sf "$(pwd)/bin/agentqa-studio" ~/.local/bin/agentqa-studio`
> (and make sure `~/.local/bin` is on `PATH`); on Windows, add this repo's `bin\`
> folder itself to your `PATH` (the shim locates the rest of the repo relative to
> its own location, so it can't be copied elsewhere). Set `AGENTQA_STUDIO_PORT` to
> use a port other than `7332`.
>
> On Windows, the dashboard itself runs natively — the write-test flow it drives
> still needs the Appium/iOS/Android toolchain, which is macOS/Linux-only.

---

## Using it — a typical run

1. `/agentqa-studio` → the dashboard opens, the agent attaches.
2. Type **"Write a test for logging in with a valid account"** → **Start**.
   Optionally **attach a requirements file** first (see below) — with one
   attached you can leave the box empty and the job takes the document's title.
3. Progress lines stream and the **stepper** advances
   (`map → clarify → explore → identifiers → build → verify → write → green →
   review → capture`).
4. A **Clarify** card appears — confirm success / failure / blockers → **Submit**.
5. If the phone raises a permission prompt, OTP, or springboard pop-up during
   exploration, a **System dialog** card asks how to handle it.
6. If the agent needs to write somewhere the allowlist doesn't cover — app
   source, most often, to add an accessibility identifier — a **Permission**
   card asks you to approve or reject the write.
7. Under `build.policy: human`, a **Build** card waits for you to build & install
   the app-code changes → **"I've built & installed."**
8. A **Review** card shows the additions-only diff and the generated test →
   **Approve** (or **Reject** with a note).
9. A green **result** links the test file. The agent goes back to waiting.

---

## Attaching requirements

The Agent panel takes a requirements document alongside the idea — click
**Attach requirements**, or drop the file on the card. **Markdown** (`.md`,
`.markdown`) or plain text (`.txt`) only.

Word, PDF and Pages are refused, with the export step spelled out in the error.
Studio has no document parser and adding one would mean a best-effort extraction
that can silently drop a table — a wrong requirement is worse than a refusal. In
Word: **File → Save As → Plain Text**, or paste into a `.md` file. Markdown is
worth the extra step: its headings survive, so the agent can tell your success
criteria from your blockers.

The **? How to write requirements** button opens a guide covering the four
questions the agent asks every run — when the test passes, when it fails, what
could block it, and which entry point — plus what *not* to write (it already
knows your screens, buttons and API calls) and a fillable template you can copy
or download.

What happens to the file:

- It is stored in the gitignored mailbox (`.agentqa/studio/uploads/`), so
  attaching one never dirties your repo. The job record carries a pointer, not
  the text.
- The agent reads it as an **intent artifact** — the same treatment
  `.agentqa/config.yml`'s `docs:` block gets. It **pre-fills** the Clarify card
  so you confirm-or-correct instead of retyping; it never replaces the card, and
  all four questions are still asked.
- **The live app outranks the document.** Where they disagree the app wins and
  the agent tells you about the difference. Nothing a document claims reaches
  the long-term memory store until the agent has seen it on a real screen.
- Uploads no queued job still refers to are deleted at the next attach.

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

- **Re-running `/agentqa-studio` takes over.** Only one connector can own the
  mailbox at a time, so each attach cancels the previous session, archives its
  transcript under `.agentqa/studio/archive/<timestamp>/`, and starts the
  Conversation panel clean — with a line saying what it cancelled. Anything the
  old session was running is dropped; an idea you queued but that never started
  carries over and runs. Use this deliberately when Studio is wedged (a card
  nobody is answering, or "a job is already running" on an agent that walked
  away): re-run `/agentqa-studio` and it resets.
- **The mailbox is never committed** — `.agentqa/studio/` is gitignored by the
  connector, and both the daemon and the agent enforce it.
- **The connector never modifies `agentqa-write-test`.** It is a thin transport
  adapter; the flow, its memory, and its green loop are exactly the terminal ones.
- **"No agent connected"** in the Agent panel just means no `/agentqa-studio`
  session is attached — run it in Claude Code at the repo.
- **Design deep-dive:** the architecture, protocol, and reasoning behind the agent
  bridge are kept as internal design history in the AgentQA-Workspace repo
  (`docs/superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md`),
  not shipped with the plugin.
