---
name: agentqa-studio
description: Attach a live agent to the AgentQA Studio dashboard so a mobile UI test is written and driven from the browser instead of the terminal — boots the daemon, watches the mailbox for a job, runs the agentqa-write-test flow unchanged, and routes its clarify / build / review checkpoints to browser cards. Use whenever the user wants to run AgentQA Studio, attach or connect an agent to the Studio dashboard, drive test-writing from the web UI, or answer AgentQA's test-writing checkpoints in the browser — invoked as /agentqa-studio.
license: MIT
compatibility: Same toolchain as agentqa-write-test — a repo configured by /agentqa-init init (.agentqa/config.yml plus a scaffolded .agentqa/memory/). The Studio daemon is the repo-root `studio/` package shipped with this plugin.
metadata:
  agentqa-studio-version: "1.2.0"
---

# agentqa-studio — drive test-writing from the browser

A **transport adapter**. Your job is the attach → watch → post-back loop around
[`agentqa-write-test`](../agentqa-write-test/SKILL.md), which runs exactly as
written; the only change is where the human questions go — its checkpoints become
cards in the Studio dashboard so a tester can answer without reading a wall of
terminal output. If you find yourself changing that skill's steps, memory scripts,
or green loop, stop: that breaks the guarantee that Studio and the terminal run the
identical flow.

## The mailbox

The dashboard (an always-on daemon, no AI) and the agent (you) never call each
other. They share append-only files under `.agentqa/studio/` — Studio Protocol v1:
`inbox.jsonl` (browser → agent), `outbox.jsonl` (agent → browser), `state.json`
(status + heartbeat), `uploads/` (read-only to you).

Never hand-write those files. Four tested scripts own the protocol, so this skill
can't drift from what the daemon reads:

| script | what it does |
|---|---|
| `scripts/studio-attach.py <repo>` | take the mailbox over: archive the old session, mark attached/idle, **print this session's connector id** |
| `scripts/studio-wait.py <repo> (--job \| --reply-to <qid>) [--connector <id>]` | block-poll the inbox; prints one JSON line |
| `scripts/studio-post.py <repo> <progress\|question\|result\|error> … [--connector <id>]` | append an outbox record; prints its id |
| `scripts/studio-detach.py <repo> [--connector <id>]` | mark detached/idle when the session ends |

`<repo>` is the app repo root. Every call after attach carries `--connector "$CONNECTOR"`.

Two results drive control flow:

- **`{"status":"waiting"}`** — the poll timed out under the tool cap. **Not an
  error.** Run the identical command again, in the same turn, as many times as it
  takes. That re-blocking loop is how one turn sits at a checkpoint for as long as
  the human needs while keeping the heartbeat warm.
- **`{"status":"superseded",…}`**, or `studio-post.py` exiting **3** — another
  `/agentqa-studio` took the dashboard over. The mailbox has no locking, so two
  live connectors is not a supported state; attaching is a takeover that mints a
  fresh connector id.

<critical>
**On `superseded`, stop.** Do not re-run the wait, do not post anything, do not
finish the job — another agent owns this dashboard and everything you write would
land in *their* transcript. Say one line to the user, that a newer
`/agentqa-studio` session took over and this one is standing down, and end your turn.
</critical>

Claude Code's own permission dialogs are bridged separately, by a plugin hook
rather than by you: when a write needs approval it becomes a Permission card in
the same conversation. You do nothing to make that happen. A reject denies the
tool call — that part is Claude Code's documented behavior — and the tester's
note is meant to reach you as the rejection reason; whether that delivery
actually works hasn't been confirmed, so treat a bare "the user doesn't want to
proceed" as possible even after a reason was given, and don't assume silence
means no reason was offered.

## Prerequisites

`.agentqa/config.yml` and a scaffolded `.agentqa/memory/`. If either is missing,
tell the user to run `/agentqa-init init` first (and `/agentqa-init setup` if the
toolchain isn't installed) — don't try to write a test without them.

## The loop

### 1. Attach — then fall straight into step 2, in the same turn

Boot the dashboard if it isn't up, then attach. Booting is **best-effort**: the
mailbox files are the source of truth, so the job still runs even if the viewer
never comes up. Never abort a run because the daemon failed to start.

```bash
# App repos need not be git repos — fall back to cwd, exactly like the launcher does.
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if ! nc -z 127.0.0.1 7332 2>/dev/null; then
  agentqa-studio >/tmp/agentqa-studio.log 2>&1 &   # M1 launcher; self-resolves the repo + opens a browser
fi
CONNECTOR="$(python3 scripts/studio-attach.py "$REPO")"
echo "connector: $CONNECTOR"
```

Attach cancels and archives any earlier session; its stderr names what it cancelled
or carried over. If it cancelled a job, tell the user in one line so a disappearing
run is never a mystery.

<critical>
**Do not end your turn after attaching.** Attaching only writes `state.json` — it
starts nothing. The only thing that ever consumes a job is `studio-wait.py`, and it
runs only while your turn is running. If you stop here to announce the URL and ask
what to test, your turn ends, no waiter exists, and every idea the user types in the
browser sits in `inbox.jsonl` at **queued** forever. The launcher already opened the
browser — they do not need an announcement from you. Go to step 2 now, same turn.
</critical>

### 2. Watch for a job

If the user already gave you the test idea (as `/agentqa-studio <idea>`, or in
chat), skip this step — the browser box and the chat start the same job. Otherwise
block on the mailbox:

```bash
python3 scripts/studio-wait.py "$REPO" --job --connector "$CONNECTOR"
```

On `answered`, take `record.flow_idea` as the test idea and go to step 3. **If the
record carries a `requirements` key, read
[`references/requirements-doc.md`](references/requirements-doc.md) first** — a user
uploaded a spec with the job. On `waiting`, re-run the same command; ending the turn
instead is the one failure this skill must never produce.

### 3. Delegate to agentqa-write-test

Read that skill and follow it for that idea, **unchanged** — steps 0–9, the memory
scripts, the green loop, all of it. The only deltas are the requirements document
above and step 4 below.

### 4. Redirect the human touchpoints to the mailbox

Wherever `agentqa-write-test` would stop and ask the human in the terminal, post a
`question` and block for the matching `reply`. Capture the printed question id,
then wait on it:

```bash
QID="$(python3 scripts/studio-post.py "$REPO" question --kind confirm --subtype build \
       --prompt 'Build & install the app onto the booted simulator, then confirm.' \
       --connector "$CONNECTOR")"
python3 scripts/studio-wait.py "$REPO" --reply-to "$QID" --connector "$CONNECTOR"  # re-run while it says waiting
```

| write-test pause | when | post | the reply carries |
|---|---|---|---|
| **Step 2 — clarify** (success / failure / blockers, + entry-point if >1) | every job | `question --kind form --subtype clarify --prompt … --questions '<json>'` | `answers:{qid:val}` — apply as the clarify answers, then write `.session-requirement.md` as write-test dictates |
| **Step 3 — system-view ask** (permission / OTP / springboard: allow / deny / dismiss) | when one appears | `question --kind form --subtype ask --prompt … --questions '<json: one choice field>'` | `answers:{qid:val}` — apply the chosen action |
| **Step 5 — build** | **only `build.policy: human`** | `question --kind confirm --subtype build --prompt …` | `decision:"built"` — then continue to step 6 |
| **Step 8 — review** | every job | `question --kind review --subtype review --prompt … --diff "$(cd "$REPO" && git diff)" --test-files '<json: [{path,content}]>'` | `decision:"approve"\|"reject"`, optional `note` — approve → capture; reject → address the note like a terminal rejection and re-present |

Two things keep the cards faithful to the flow:

- **`--questions`** is a JSON array of `{qid,label,kind,options?,default?}`. Ask the
  three questions write-test always asks as `text` fields; add an `entry` `choice`
  field only when step 0 found more than one entry point. When step-0 docs already
  answer a question, pass that answer as the field's `default` — same
  confirm-or-correct behavior as the terminal flow.
- **`options`** on a `choice` field is a list of bare strings, or `{"label":…,"value":…}`
  pairs when the button text and the answer you want back differ. The browser shows
  `label` and replies with `value`. An object missing either renders as raw JSON on
  the button — that's the tell a question was built wrong.

### 5. Post progress as you work

The silent stretches — indexing, exploring with agent-device, adding identifiers,
verifying, the green loop — emit `progress` so the browser timeline and stepper
move. `--stage` takes one of `map · clarify · explore · identifiers · build ·
verify · write · green · review · capture`.

```bash
python3 scripts/studio-post.py "$REPO" progress --stage explore \
  --text 'Exploring the login flow with agent-device' --connector "$CONNECTOR"

python3 scripts/studio-post.py "$REPO" result --status green \
  --summary 'login test passing' --test-path 'AutomationTests/tests/test_login.py' \
  --connector "$CONNECTOR"
```

If the run is abandoned, post `result --status abandoned --summary …` plus an
`error --text …` with the reason, then let write-test's own cleanup delete the
working-layer files — you don't manage those here.

### 6. Loop or detach

After a `result`, go back to step 2 and watch for the next job — still the same
turn. When the user ends the session:

```bash
python3 scripts/studio-detach.py "$REPO" --connector "$CONNECTOR"
```

so the dashboard shows the agent is gone rather than a stale `attached: true`.

---

When the dashboard is in a state that doesn't match what you expect — stuck at
*queued*, a job that vanished, the viewer never came up — see
[`references/troubleshooting.md`](references/troubleshooting.md).
