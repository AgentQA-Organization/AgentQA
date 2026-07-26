# The write-test workflow

What actually happens when you run `/agentqa-write-test <idea>`: the stages a run
moves through, the three points where it stops for you, and the loop that runs the
test until it's green.

This page is the mechanics. For the *principles* that keep the output trustworthy
(how to phrase a good idea, why identifiers are additive, "never loosen an
assertion"), see [`writing-tests.md`](writing-tests.md). For *why* it's shaped this
way, see [`architecture.md`](architecture.md).

## The lifecycle

A run advances through these stages (the same sequence the Studio stepper shows):

```
map → clarify → explore → identifiers → build → verify → write → green → review → capture
```

| Stage | What the agent does |
|---|---|
| **map** | When a CodeGraph index exists, grounds itself in the flow's screen graph — source code as the white-box tool — before touching the app. |
| **clarify** | Asks the one thing neither the code nor the app can answer: **what is the expected user outcome?** Pins it as a one-sentence assertion. One batched round of questions, pre-filled from your product docs when available. |
| **explore** | Recalls what memory already knows about *this flow*, then drives the flow with `agent-device` and reconciles against live `page_source` — because a build can replace native login with web SSO, and only the live hierarchy is truth. |
| **identifiers** | Adds accessibility identifiers **additively**, following your config's convention. `git diff` on app code must show zero deletions. |
| **build** | Under `build.policy: human`, stops and asks you to build & install onto the booted device. Under `build.policy: agent`, builds itself. |
| **verify** | Pulls `page_source` and confirms every new identifier actually shows up before writing locators against it. |
| **write** | Writes the pytest test — your identifiers for app-owned UI, visible-label predicates only for UI you don't own. |
| **green** | Runs the test until it passes (the green loop, below). |
| **review** | Shows you the additions-only app-code diff and the generated test for approval. |
| **capture** | Writes deduped observations back to `.agentqa/memory/`. |

On a **repeat** run for a known flow, the agent uses the flow note as a *map* and
only deep-dives where the app has diverged from memory — fast, but still grounded
in the live app. See [`memory.md`](memory.md).

## The three human checkpoints

The flow hands control back to you at exactly three points (plus any device
permission prompts during exploration):

| Checkpoint | When | You decide |
|---|---|---|
| **Clarify** | every run | what *success*, *failure*, and *blockers* look like |
| **Build** | only under `build.policy: human` | build & install the app-code changes, then hand back |
| **Review** | every run | approve or reject the additions-only diff and the test |

With AgentQA Studio these become clickable browser cards instead of terminal
questions — the flow is otherwise identical. See
[`agentqa-studio.md`](agentqa-studio.md).

## The green loop

`green` is not a single pytest invocation — it's a loop:

```
preconditions → pytest → diagnose from saved artifacts → fix → repeat
```

`conftest.py` saves `page_source` + a screenshot on any failure and writes a
per-run runbook to `artifacts/runbook/`, so a failure is diagnosed from captured
evidence rather than re-run blindly. The agent runs until the test passes — or
until it concludes the failure is a real bug, which is a finding, not something to
weaken the assertion over (see [`writing-tests.md`](writing-tests.md)).

## Running an existing suite

Running tests is part of this same skill's green loop. Ask it to run the suite and
it offers two modes:

- **pytest-only (lean)** — just the pytest output.
- **full diagnosis** — recalls the `failures/` library, diagnoses a failure inline
  from the saved artifacts, and captures any new signature it finds.

## Flaky runs

The `failures/` memory is a shared library of phantom/flaky signatures across all
flows. When a known phantom recurs (e.g. stale app state from an aborted run, or a
WebDriverAgent timeout under load), its remedy is recognized and applied **once**
automatically, then escalated if it doesn't clear — rather than re-diagnosed from
scratch every time. Because failures are deliberately *not* scoped to one flow, a
signature learned on checkout is available when login times out the same way.

## See also

- [`writing-tests.md`](writing-tests.md) — the discipline that keeps output trustworthy
- [`memory.md`](memory.md) — recall, capture, and the failures library
- [`architecture.md`](architecture.md) — why the flow is shaped this way
- [`agentqa-studio.md`](agentqa-studio.md) — the same flow, driven from a browser
- [`configuration.md`](configuration.md) — `build.policy` and the other run-shaping settings
