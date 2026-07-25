---
name: agentqa-studio
description: Attach a live agent to the AgentQA Studio dashboard so a mobile UI test can be written and driven from the browser instead of the terminal. Boots the Studio daemon, watches the mailbox for a "write a test for ___" job, runs the existing agentqa-write-test flow unchanged, and routes its three human checkpoints (clarify, build, review) plus any step-3 system-view prompts to browser cards. Use this whenever the user wants to run AgentQA Studio, connect/attach an agent to the Studio dashboard, drive test-writing from the web UI, or answer AgentQA's test-writing checkpoints in the browser — invoked as /agentqa-studio.
license: MIT
compatibility: Same toolchain as agentqa-write-test (a project configured by /agentqa-init init, with .agentqa/config.yml and a scaffolded .agentqa/memory/). The Studio daemon is the repo-root `studio/` package shipped with this plugin.
metadata:
  agentqa-studio-version: "1.0.0"
---

# agentqa-studio — drive test-writing from the browser

This skill is a **transport adapter**. It runs the existing
[`agentqa-write-test`](../agentqa-write-test/SKILL.md) flow **exactly as written**
and changes only one thing: *where the human questions go*. In a normal
`/agentqa-write-test` session the three human checkpoints and the step-3
system-view prompts are answered in the terminal. Here they become cards in the
AgentQA Studio web dashboard, so a tester can watch progress and answer without
reading a wall of terminal output.

Because it is an adapter, it **never edits or re-implements `agentqa-write-test`**.
If you find yourself changing that skill's steps, memory scripts, or green loop,
stop — that is out of scope and breaks the guarantee that Studio and the terminal
run the identical flow. Your job is the attach → watch → post-back loop around it.

## How the two halves talk — the mailbox

The dashboard (an always-on daemon, no AI) and the agent (this session, the AI)
never call each other directly. They share three append-only files under
`.agentqa/studio/` in the app repo — the **Studio Protocol v1 mailbox**:

- `inbox.jsonl` — browser → agent (`job`, `reply`)
- `outbox.jsonl` — agent → browser (`progress`, `question`, `result`, `error`)
- `state.json` — attach/run status + heartbeat

You never hand-write these files. Four tested helper scripts do it, so this skill
stays thin and can't drift from the protocol the daemon reads:

| script | what it does |
|---|---|
| `scripts/studio-attach.py <repo>` | ensure the mailbox + its `.gitignore`, mark attached/idle |
| `scripts/studio-wait.py <repo> (--job \| --reply-to <qid>)` | block-poll the inbox; prints one JSON line |
| `scripts/studio-post.py <repo> <progress\|question\|result\|error> …` | append an outbox record; prints its id |
| `scripts/studio-detach.py <repo>` | mark detached/idle when the session ends |

`<repo>` is the app repo root — the git top level of your current directory. Set
it once: `REPO="$(git rev-parse --show-toplevel)"`.

`studio-wait.py` prints `{"status":"answered","record":{…}}` when the awaited
job/reply lands, or `{"status":"waiting"}` when it times out under the tool cap.
**`waiting` is not an error — run the same wait again to re-block.** That is how a
single turn can sit at a checkpoint for as long as the human needs while keeping
the heartbeat warm.

## Prerequisites

Same as `agentqa-write-test`: the repo needs `.agentqa/config.yml` and a
scaffolded `.agentqa/memory/`. If either is missing, tell the user to run
`/agentqa-init init` first (and `/agentqa-init setup` if the toolchain isn't
installed) — don't try to write a test without them.

## The loop

### 1. Attach

Boot the dashboard if it isn't already up, then attach. Booting is **best-effort**:
the mailbox files are the source of truth, so the job still runs even if the
viewer never comes up — never abort the run because the daemon failed to start.

```bash
REPO="$(git rev-parse --show-toplevel)"
# Best-effort: start the viewer if port 7332 is closed.
if ! nc -z 127.0.0.1 7332 2>/dev/null; then
  agentqa-studio >/tmp/agentqa-studio.log 2>&1 &   # M1 launcher; self-resolves the repo + opens a browser
fi
python3 scripts/studio-attach.py "$REPO"
```

Tell the user the dashboard is at http://127.0.0.1:7332/ and that they can type
the test idea there (or in chat — either works).

### 2. Watch for a job

```bash
python3 scripts/studio-wait.py "$REPO" --job
```

If it prints `{"status":"waiting"}`, run it again. On `{"status":"answered",…}`,
take `record.flow_idea` as the test idea. (If the user has already told you the
idea in chat, you can proceed with that instead of waiting — the browser box and
the chat are two ways to start the same job.)

### 3. Delegate to agentqa-write-test

Run the `agentqa-write-test` flow for that idea, **unchanged** — steps 0–9, the
memory scripts, the green loop, all of it. Read that skill and follow it. The only
difference is step 4 below.

### 4. Redirect the human touchpoints to the mailbox

Wherever `agentqa-write-test` would stop and ask the human in the terminal, post a
`question` and block for the matching `reply` instead. Post the question, capture
the printed question id (`QID`), then wait on it:

```bash
QID="$(python3 scripts/studio-post.py "$REPO" question --kind confirm --subtype build \
       --prompt 'Build & install the app onto the booted simulator, then confirm.')"
python3 scripts/studio-wait.py "$REPO" --reply-to "$QID"   # re-run while it says waiting
```

The four touchpoints and how they map:

| write-test pause | when | post | the reply carries |
|---|---|---|---|
| **Step 2 — clarify** (success / failure / blockers, + entry-point if >1) | every job | `question --kind form --subtype clarify --prompt … --questions '<json>'` | `answers:{qid:val}` — apply as the clarify answers, then write `.session-requirement.md` as write-test dictates |
| **Step 3 — system-view ask** (permission / OTP / springboard: allow / deny / dismiss) | when one appears | `question --kind form --subtype ask --prompt … --questions '<json: one choice field>'` | `answers:{qid:val}` — apply the chosen action |
| **Step 5 — build** | **only `build.policy: human`** | `question --kind confirm --subtype build --prompt …` | `decision:"built"` — then continue to step 6 |
| **Step 8 — review** | every job | `question --kind review --subtype review --prompt … --diff "$(cd "$REPO" && git diff)" --test-files '<json: [{path,content}]>'` | `decision:"approve"\|"reject"`, optional `note` — approve → capture; reject → address the note like a terminal rejection and re-present |

Notes that keep the cards faithful to the flow:

- **Clarify `--questions`** is a JSON array of `{qid,label,kind,options?,default?}`.
  Ask the three questions write-test always asks (success, failure, blockers) as
  `text` fields; add an `entry` `choice` field only when step 0 found more than one
  entry point. When step-0 docs already answer a question, pass that answer as the
  field's `default` — same "confirm-or-correct, don't ask cold" behavior as the
  terminal flow.
- **Build card** only exists under `build.policy: human`. Under `agent`, write-test
  builds itself — post no build question.
- **Review** carries the additions-only diff and the test file(s); after approval,
  finish step 9 (capture) as write-test dictates.

### 5. Post progress as you work

The silent stretches — indexing, exploring with agent-device, adding identifiers,
verifying, the green loop — emit `progress` so the browser timeline and stepper
move. Tag each with the phase it belongs to (optional but nice; the stepper reads
the slug):

```bash
python3 scripts/studio-post.py "$REPO" progress --text 'Exploring the login flow with agent-device' --stage explore
```

Stage slugs: `map · clarify · explore · identifiers · build · verify · write ·
green · review · capture`.

When the run finishes green:

```bash
python3 scripts/studio-post.py "$REPO" result --status green \
  --summary 'login test passing' --test-path 'AutomationTests/tests/test_login.py'
```

If the run is abandoned, post `result --status abandoned --summary …` (and an
`error --text …` with the reason), then let write-test's own cleanup delete the
working-layer files — you don't manage those here.

### 6. Loop or detach

After a `result`, go back to step 2 and watch for the next job. When the user ends
the session, detach so the dashboard shows the agent is gone:

```bash
python3 scripts/studio-detach.py "$REPO"
```

## Background

Design and rationale (the brainless-daemon / independent-worker boundary, the
protocol, the pause-point mapping) live in
[the M2 design spec](../../docs/superpowers/specs/2026-07-25-agentqa-studio-m2-agent-bridge-design.md).
You don't need it to run the loop, but read it if a decision here seems arbitrary.
