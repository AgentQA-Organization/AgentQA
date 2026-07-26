# Writing good tests

`/agentqa-write-test <idea>` follows a disciplined flow — the rules below are what
keep the generated tests trustworthy. This page is the *discipline*; the stage-by-
stage mechanics are in [`workflow.md`](workflow.md).

## Give it a concrete assertion, not a screen name

The single most important thing you provide is **what "pass" means**.

```text
/agentqa-write-test "log in with a valid account lands on the home tab"
```

"Logging in with a **valid** account lands on the home tab" tells the agent what
success is; "test login" does not. Everything else — screens, fields, validations,
navigation, APIs — the agent discovers itself from the source code (white-box) and
the running app (black-box). Your job is to pin the outcome that neither the code
nor the app can tell it.

## The seven rules

1. **Map to code, then nail the assertion.** When a CodeGraph index exists, the
   agent grounds itself in the flow's screen graph *first*, then asks you the one
   thing neither the code nor the app can answer — **what is the expected user
   outcome?** — and pins it as a one-sentence assertion. No open-ended
   brainstorming; one batched round of questions.

2. **Recall, then explore the real app.** It loads what memory already knows about
   *this flow*, then drives the flow with `agent-device` and reconciles against
   live `page_source` — because a real build can replace native login with web
   SSO, and only the live hierarchy is truth.

3. **Identifiers are added additively.** Accessibility identifiers follow your
   config's convention and change **nothing** about behavior, layout, or logic —
   `git diff` on app code must show **zero deletions**.

4. **You build; the agent verifies.** Under `build.policy: human` the agent stops
   and asks you to build & install onto the booted device (right when CLI builds
   are slow or signing is involved — common on iOS), then pulls `page_source` and
   confirms every new identifier actually shows up before writing locators against
   it.

5. **Locators, honestly.** Your identifiers for app-owned UI; visible-label
   predicates only for UI you don't own (web views). Credentials come only from
   the env vars named in the config — never hardcoded, never committed.

6. **Green, then reviewed.** The agent runs until the test passes (its green loop:
   preconditions → pytest → diagnose from the saved artifacts), then shows you the
   additions-only app-code diff and the test for approval.

7. **Never loosen an assertion to make a test pass.** A failing test that reflects
   a real bug is a **finding**, not something to weaken.

## See also

- [`workflow.md`](workflow.md) — the lifecycle these rules are enforced across
- [`configuration.md`](configuration.md) — the identifier convention, build policy, and credential env vars these rules read from
- [`memory.md`](memory.md) — how recall grounds rule 2, and how the intent layer feeds the clarify step
- [`architecture.md`](architecture.md) — why the live app outranks the source and the docs
