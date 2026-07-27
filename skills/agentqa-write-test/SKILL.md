---
name: agentqa-write-test
description: Turn a natural-language test-case idea into a reviewed, passing Appium test (iOS/XCUITest or Android/UiAutomator2) — index and map the flow to code, pin what success, failure, and blockers look like with the user, explore the real app with agent-device until the whole flow is understood, add accessibility identifiers additively, verify them in the live hierarchy, then write the test and run it until green. Also owns the behavioral-memory store the tests are built from. Use when the user wants a UI test written, generated, updated, or run for a flow. Invoked as /agentqa-write-test <idea>.
license: MIT
compatibility: iOS (macOS + Xcode + a simulator) or Android (Android SDK + an emulator/device + a JDK); needs the toolchain from /agentqa-init setup and a project configured by /agentqa-init init
metadata:
  agentqa-write-test-version: "1.3.0"
---

# agentqa-write-test — idea → identifiers → Appium test

Turn a natural-language test-case idea into a reviewed, passing Appium test.
Requires `.agentqa/config.yml` and a scaffolded `.agentqa/memory/` — if either is
missing, run `/agentqa-init init` first (and `/agentqa-init setup` if the
toolchain isn't installed). Read the config and the host repo's agent docs before
starting; don't re-derive them.

This skill is self-contained: the memory schema, the clarify checklist, and the
memory scripts all live here. It never spawns sub-agents — every step,
including failure diagnosis, runs inline in your own context.

## Platform — iOS or Android

`platform:` in `.agentqa/config.yml` selects the target. **The flow below (steps
0–9), the checkpoints, the clarify questions, and the memory model are identical
on both platforms** — what differs is a handful of concrete mechanics: the device
+ driver, the data reset, the accessibility-identifier mechanism, how system
dialogs are handled, and the green-loop preconditions. This file's concrete
commands are written for **iOS**; when `platform: android`, read
**[references/android.md](references/android.md)** and use its equivalent
wherever a step shows an iOS-specific command (`xcrun`/`simctl`, the app's
`bundle_id`, `accessibilityIdentifier`). The app id is the `bundle_id` on iOS and
the `app_package` on Android — `reset-app-data.sh` and `agent-device` resolve it
from the config for you. Everything else you read here applies verbatim.

## Project configuration

`.agentqa/config.yml` at the host repo root holds bundle id, test directory,
build policy, credential env var names, and identifier convention. Never hardcode
project facts in tests, and never commit credentials — accounts flow through the
env vars named in the config.

**Product artifacts (`docs:`, optional).** If the config declares `docs:` — local
paths/globs pointing at SRDs, PM scenarios, user flows, acceptance criteria — those
files are an **intent layer**: what the app is *meant* to do. Read them in step 0
and use them to pre-fill step 2. They are read-only (never write to them) and they
never outrank the live hierarchy. Most repos won't have the block at all; when it's
absent, skip it and proceed exactly as you would otherwise — its absence is normal,
not a blocker, and not something to ask the user about. Full rules:
[references/memory-model.md](references/memory-model.md).

**Build policy (respect it strictly).** `build.policy` decides who builds:
- `human` — stop after any app-code change and ask the user to build & install
  onto the booted device; never run the app build yourself (`xcodebuild` on iOS,
  `./gradlew` on Android).
- `agent` — the agent may build/install itself.

**Reset policy.** `reset_app_data` (default `always`) decides whether the app's
local data is wiped before every launch. `conftest.py` handles it for pytest runs;
for the `agent-device open` launches in step 3 you call `agentqa-init`'s
`scripts/reset-app-data.sh` yourself, so exploration sees the same starting state
the test will. It reads `platform:` and wipes the right way (`simctl` container on
iOS, `adb shell pm clear` on Android). `never` → don't reset, and expect state
carried over from earlier runs.

Behavioral knowledge lives in `.agentqa/memory/` — schema:
[references/memory-model.md](references/memory-model.md).

## The Flow

0. **Index, then map to code** — run `codegraph init` **first** (idempotent: it
   builds the index, or refreshes a stale one), then `codegraph explore "…"` for
   the flow's screens/symbols + blast radius, then **read the source files it
   points at**. Ground yourself in the screen graph BEFORE committing to an
   assertion. Indexing is CPU-heavy — finish it here, before any simulator work;
   never run it while the simulator or a test suite is running.

   **Then, if `config.yml` declares `docs:`, read the artifacts covering this
   flow.** Skim for what the team already wrote down about it: intended outcome,
   acceptance criteria, error states, preconditions, known edge cases. You now hold
   two priors — the code's structure and the product's intent — and step 3 checks
   both against the live app. Scope it: `docs:` can match a whole specification
   library, and you want the sections about *this* flow, not every page of it —
   grep for the flow's screens and terms and read around the hits. No `docs:`
   block, nothing matching this flow, or a path that no longer resolves? Move on
   without comment; most repos have no such docs and the flow is unchanged.
1. **Recall — this flow's slice, not the whole store.** `index.md` is generated
   and gitignored, so rebuild it, then read only what this flow needs:

   ```bash
   python3 scripts/memory-index.py .agentqa/memory                 # rebuild the index
   python3 scripts/memory-index.py .agentqa/memory --flow <flow>   # this flow's slice
   python3 scripts/memory-index.py .agentqa/memory --stale         # what needs re-verifying
   ```

   Read the detail notes the slice names. Loading the whole store instead is
   fine at ten notes and quietly ruinous at two hundred — the point of the tag
   scoping is that a mature store costs a run no more than a young one. Nothing
   matched? That's a new flow, not an error: there's nothing to verify-delta
   against, so explore it from scratch. The `--stale` list is the identifiers
   whose verification has aged out — you'll be standing on those screens in step
   3 anyway, so confirm them there rather than trusting the date. Schema:
   [references/memory-model.md](references/memory-model.md).
2. **Clarify success, failure, and blockers** — do NOT open-ended brainstorm.
   Follow [references/clarify.md](references/clarify.md): one batched round.
   **Three questions are always asked, every run, never inferred:** what does
   this flow look like when it **succeeds**, what does it look like when it
   **fails**, and what could **block** the test (permission prompts, OTP/2FA,
   required test data, backend state). Add a fourth when step 0's map shows the
   flow has **more than one entry point** (login from a welcome screen, an
   account tab, a 401 bounce): which one should the test enter through? List the
   ones you found — the options are discoverable, the choice isn't. Add
   environment / objective / preconditions only when `config.yml` and `env.md`
   don't already answer them.

   **When step 0's artifacts already answer one of these, propose it back instead
   of asking cold** — "the spec says a wrong password shows an inline error under
   the field; still true?" beats an open question the user already wrote the answer
   to, and it shows you read their docs. The three questions are still *asked* every
   run — what changes is their form, from blank to confirm-or-correct. Never let a
   doc skip a question or stand in for the user's answer: specs go stale, and the
   user is the one who decides what this test must prove. Where the artifacts are
   silent, ask normally.
   One round is the budget for *requirements*. Blockers and divergences you hit
   live in step 3 are escalated when you hit them — that's required, not a
   second round.
   Then write the answers to `.agentqa/memory/.session-requirement.md` — the
   ephemeral requirement summary every later step checks itself against (Working
   layer; schema in [references/memory-model.md](references/memory-model.md)).
   Output: a confirmed one-sentence assertion, the failure criteria, the known
   blockers, and the edge cases you'll cover.
3. **Explore the REAL app with `agent-device`** — always, yourself, inline, and
   only after step 0's `codegraph init` + source read gave you the expected
   screen graph. Order is fixed: **index → read the source → drive the live app**.

   **No Appium in this step. At all.** No Appium session, no Appium MCP
   `page_source` read, no pytest/Appium script "just to poke around". Appium
   enters at step 6, and the first test file is written once, at step 7 — earlier
   means testing before you know what to assert. Here `agent-device snapshot` IS
   the live hierarchy, and it is your source of truth; code reading lies.
   Never spawn a sub-agent for this either.

   Drive the CLI directly: `agent-device open <app_id>` — the app id is the
   `bundle_id` (iOS) or `app_package` (Android) from the config; add
   `--platform android` on Android so agent-device selects the right target. (When
   `reset_app_data: always` in `config.yml`, wipe first with `agentqa-init`'s
   `scripts/reset-app-data.sh`, so exploration starts where the tests will) →
   `agent-device snapshot -i` → `agent-device press`/`fill <id> --settle`. Do the
   **verify-delta** pass: use the flow note — and whatever the step-0 artifacts
   claim about this flow — as your map, confirm each known waypoint against live
   state, deep-dive only where reality diverges. A spec is a claim exactly like a
   memory note; when the build disagrees with one, **say so** — a doc that no
   longer matches shipped behavior is something the user will want to know.
   Where snapshots are
   sparse (web/auth sheets), fall back to `agent-device screenshot` + coordinate
   taps. Cross-check what you see against the CodeGraph map from step 0 (which
   view/controller renders this screen) for symbol-level detail before writing
   notes.

   **Leave only with the full picture.** Every step from entry to the success
   state, the failure path, and each blocker named in
   `.session-requirement.md` must have been observed live. If any part of the
   flow is still a guess, keep driving — never close the gap from source code,
   and never start writing a test to "find out".

   **Watch for system views on every snapshot/screenshot** — permission prompts
   (location, notifications, Face ID/Touch ID, camera/photos), low-storage
   alerts, springboard pop-ups. These sit outside the app's own hierarchy and
   block the flow. Don't guess a dismissal — stop and ask the user what action
   to take (allow, deny, or dismiss) before continuing. Asking here is expected;
   it is not a second clarify round.

   **A system view you saw is a system view the test will hit.** Under
   `reset_app_data: always` the wipe restores the permission state, so the same
   prompt fires on *every* launch — the suite meets it as often as you did.
   Record it in the screen note as `[quirk]` with the user's chosen action, and
   carry it into step 7 as setup the test performs before the flow starts, not
   as a step buried mid-test. Because these views are outside the app hierarchy,
   the app's own identifiers can never address them: match the button by its
   visible label, or use the driver's alert handling. A test that assumes a
   clean first screen is a test that fails on a fresh simulator.

   Write to `.agentqa/memory/` before moving to step 4: create/refresh each
   note's frontmatter, then add every observation through
   `scripts/memory-write.py` (`propose` → `apply --op ADD|UPDATE|DELETE|NOOP`).
   Read the three lines `propose` prints rather than just the score — the ranking
   is textual, so it catches restatements and misses the same fact worded
   differently. Full schema:
   [references/memory-model.md](references/memory-model.md).
   - `flows/<flow>.md`: `[flow-step]` nav path, `[assertion]`, `[edge-case]`s,
     `[native]`/`[web]` per step.
   - `screens/<screen>.md` per screen: `[native]`/`[web]`, `[quirk]`s, and any
     observed identifier as `[identifier] <name> → <file/symbol>;
     added-unverified <today> #<flow>`.
   - **Tag every observation with its flow** (`#login`). The tag is the only
     thing tying a screen note to the flows that traverse it, so an untagged
     observation is in the store but invisible to the next run's scoped Recall —
     it may as well not have been written. A screen three flows pass through
     carries all three tags.
   - Write terse notes (facts, not narration); one-line `summary:` in
     frontmatter. Then rebuild and check:
     `python3 scripts/memory-index.py .agentqa/memory` and
     `python3 scripts/memory-lint.py .agentqa/memory`.
   - **Only what you observed live goes in.** A claim you read in an artifact and
     never saw in the hierarchy stays in `.session-requirement.md` and dies with
     the session. `flows/`, `screens/`, and `failures/` are the store later runs
     trust as a map — an unverified doc claim in there is indistinguishable from a
     fact you earned by driving the app, and it would mislead every run after this
     one. (`memory-write.py` refuses to write to the session files or the
     generated index, so the mechanical half of this is handled; the judgement
     half is yours.)
4. **Add accessibility identifiers** — strictly additive app-code changes per the
   config's `identifier_convention`; never behavior, layout, or logic. The
   **mechanism is platform-specific**: iOS sets `accessibilityIdentifier`;
   Android sets a `contentDescription` (or a Compose `testTag` exposed as
   `resource-id`) — the additive strategies and the exact page_source shape to
   expect are in [references/android.md](references/android.md). Whichever
   platform, log each new one as `[identifier] <name> → <file/symbol>;
   added-unverified <today> #<flow>` in the screen note. Verify with
   `git diff --numstat`: deletions must be 0.
5. **Build checkpoint** — first write `.agentqa/memory/.run-checkpoint.md` (Working
   layer; schema in [references/memory-model.md](references/memory-model.md)): the
   `added-unverified` identifiers from step 4, the assertion from step 2, and
   `Blocker: WAITING_FOR_HUMAN_BUILD` (the failure criteria and blockers stay in
   `.session-requirement.md`, which survives the pause too — don't re-ask for
   them). Then per `build.policy`: `human` → stop and
   ask the user to build & install onto the booted simulator, then continue;
   `agent` → build yourself. The checkpoint lets step 6 resume after a context
   break instead of re-clarifying and re-exploring.
6. **Verify identifiers in the live hierarchy** — resume from
   `.agentqa/memory/.run-checkpoint.md` (don't re-ask the human or re-explore); pull
   Appium `page_source` (via the Appium MCP if present, else shell out) and grep
   for the new names (iOS: `name="…"`; Android: `content-desc="…"` or
   `resource-id="…/…"` — see [references/android.md](references/android.md)). On
   success, **refresh** each identifier observation to
   `verified-in-hierarchy <today>`. Missing → fix the identifier's placement in
   app code (Swift on iOS, the View/Compose node on Android), back to 5.
7. **Write page object + test** under `<test_dir>/pages|tests/`. Locators: your
   identifiers for app-owned UI (iOS: accessibility-id / predicate; Android:
   accessibility-id for a content-desc, or resource-id / UiAutomator — see
   [references/android.md](references/android.md)); visible-label predicates only
   for UI you don't own (web views, and system dialogs — neither can carry your
   identifiers). Credentials only via the env-var names in the config. Assert
   the success criteria from `.session-requirement.md`, and let the failure
   criteria shape the negative/edge cases. Under `reset_app_data: always` the
   session starts on a wiped app — the test must establish its own state (log in,
   seed data) and can never rely on what a previous run or a manual setup left
   behind. **Every system view step 3 recorded gets handled in setup**, with the
   action the user chose, before the flow under test begins — a permission
   prompt nobody dismisses blocks the run exactly the way it blocked your
   exploration. Enter the flow through the entry point pinned in step 2.
8. **Run until green** — the green loop below. Then the **review checkpoint**:
   present the app-code diff (additions only) and the test to the user for
   approval.
9. **Capture** — dedup/refresh memory via `scripts/memory-write.py` (propose →
   apply; see [references/memory-model.md](references/memory-model.md)) and record
   test-writing lessons; rebuild the index with
   `python3 scripts/memory-index.py .agentqa/memory` and validate the store with
   `python3 scripts/memory-lint.py .agentqa/memory` (it catches the quiet
   corruptions — a note with no `summary:`, a mistyped category, an untagged
   observation — that leave the store looking healthy while answering nothing);
   delete **both** Working-layer
   files — `.agentqa/memory/.run-checkpoint.md` and
   `.agentqa/memory/.session-requirement.md` — the session is over and they are
   never carried into the next one; re-index CodeGraph (never while tests are
   running). Abandoning a run counts as the end of the session: delete them then
   too.

**Ownership:** you own every note end-to-end, in one context — `flows/`+`screens/`
exploration notes (step 3), identifier verification-status updates (step 6),
test-outcome notes (step 8/9), and failure signatures (green loop). No hand-off,
no sub-agents anywhere in this skill.

**The store is markdown, and only four places in it are yours to write:**
`flows/`, `screens/`, `failures/`, `env.md`. `index.md` is regenerated (edits
there vanish on the next rebuild) and the two dotfiles are this session's scratch
state (writes there leak unverified claims into what later runs trust).
`memory-write.py` enforces the boundary, so you'll get a clear refusal rather
than a silent loss.

## The green loop (step 8, and any bare "run the tests" request)

### Preconditions (check, don't assume)

```bash
# iOS
xcrun simctl list devices booted | grep -q Booted     # simulator up
xcrun simctl listapps booted | grep -q <bundle_id>    # app installed
nc -z 127.0.0.1 4723                                  # appium server up

# Android
adb devices | awk '$2=="device"' | grep -q .          # device/emulator up
adb shell pm list packages | grep -q <app_package>    # app installed
nc -z 127.0.0.1 4723                                  # appium server up
```

Device or app missing → per `build.policy`: ask the user (human) or
build/install yourself (agent). Appium down → start it in the background:
`appium --log-level warn` (on iOS the first-ever session builds WebDriverAgent —
takes minutes once; on Android the first session installs the UiAutomator2
server APKs).

### Run

```bash
cd <test_dir>
<CRED_ENV>=<ask user; never commit> .venv/bin/pytest tests -v   # full suite
.venv/bin/pytest tests/test_<flow>.py -v                        # one file
```

Credential-gated tests should skip cleanly when their env var is unset — ask the
user for a test account rather than inventing one. The `conftest.py` fixture
wipes the app's data before the session when `reset_app_data: always`, so every
run starts from the same clean state — a suite that only passes on the second run
is depending on leftover state.

**Asked only to run existing tests, with no test to write?** Ask first:
**pytest-only (lean)** or **full diagnosis**? Lean = run the command, print the
output, stop — no `failures/` recall, no diagnosis, no Capture. Full = the rest
of this section.

### On failure — diagnose, then act

Diagnose it yourself, inline, evidence first. Recall `.agentqa/memory/failures/`
and the flow note for the failing test, then read the evidence in order: first
`<test_dir>/artifacts/failed_<test>.xml` (+ `.png`) — saved at the moment of
failure by the conftest hook — then the `page_source` hierarchy. Don't re-run
before reading both.

Classify: identifier missing → back to step 4 (identifiers + rebuild) ·
locator drift → fix the page object · app misbehaves → possible real bug,
**never weaken the assertion** (a failure that matches the failure criteria in
`.session-requirement.md` is the app telling the truth — report it) · system
dialog (permission prompt/pop-up)
blocked the run → ask the user how to handle it, don't guess a tap · phantom →
match a `failures/` signature (CPU-load WDA timeout; stale state from an
aborted run).

Write the signature to `.agentqa/memory/failures/<signature>.md` (`[symptom]`,
`[cause]`, `[remedy]`, each tagged `#<flow>`) via `scripts/memory-write.py`
(`propose` → `apply`, `--op UPDATE` to refresh an existing signature instead of
duplicating), then `python3 scripts/memory-index.py .agentqa/memory` to refresh
`index.md`. Failure notes are recalled by *every* flow, not just this one — the
signature library is deliberately cross-flow, because the same WDA timeout ruins
checkout and login alike.

**Act:** anything crossing into app code or a rebuild goes back through steps
4–6 and their human checkpoints. **A known phantom with a recorded remedy →
apply the remedy exactly once (bounded, logged); if it clears, note it and
pass; if it doesn't, escalate as possibly-real and stop.**

## Rationalizations vs reality (all observed in real sessions)

| Excuse | Reality |
|---|---|
| "The idea is clear, skip the clarify step" | Map the code first, THEN pin the outcome — one-sentence ideas hide the assertion the screen graph makes obvious. |
| "The user told me what passing looks like; failure and blockers are obvious" | They aren't — "wrong password shows an inline error" vs "bounces to the start" are different tests. Ask all three, every run. |
| "Let me ask which screens/fields/APIs this flow uses" | Never-ask list. Step 0 (code) and step 3 (live app) answer those; asking tells the user you didn't look. |
| "Let's explore the design space together first" | Not a design task. Ask success/failure/blockers, then discover the rest yourself. |
| "The requirements are in my context, no need for the temp note" | Context breaks (the build pause is one). The note is what steps 3–8 check themselves against — and it's deleted when the session ends. |
| "There's already a CodeGraph index, skip `codegraph init`" | It's idempotent and cheap next to a stale map. Init, explore, read source — in that order, before the simulator. |
| "I'll just build the app myself quickly" | If build.policy is human, there's a reason (slow builds, signing). Hand off. |
| "The code shows this screen, I can write the test from it" | A real build replaced native login with web SSO. Only the live hierarchy is truth. |
| "The screenshot shows the keyboard, so tap its Go key" | Appium types without the keyboard up; the page's own submit button sat under it. Trust the live hierarchy over screenshots. |
| "The locator fails, I'll match by fuzzy label" | If your identifier is missing, fix its placement in app code, not the locator. |
| "Memory says it's native, so skip exploring" | Memory is a claim; verify-delta against the live hierarchy. The build may have changed. |
| "I'll just load the whole memory index, it's small" | It's small *today*. Scoped recall is what keeps run N+100 as cheap as run 1 — `--flow <flow>`, then the notes it names. |
| "The tag is obvious from the filename, skip it" | Scoped recall matches on `#<flow>`. An untagged observation is stored and unfindable — the worst of both. |
| "I'll fix up index.md by hand" | It's generated from the notes and gitignored. Edit the note; rebuild the index. |
| "This identifier is 40 days old but it was fine last time" | `--stale` is telling you nobody has looked since. You're on that screen in step 3 anyway — look. |
| "I'll seed the flow note from the code" | Only facts grounded in the live hierarchy belong in memory. Explore, then write. |
| "I'll write a quick Appium/pytest script to poke around the app" | That's step 7's job. Exploring means driving `agent-device` directly — a script at this point is a test written before you know what to assert. |
| "I'll just read page_source via the Appium MCP while exploring" | Step 3 is agent-device only; Appium enters at step 6. `agent-device snapshot` already gives you the live hierarchy. |
| "I've seen the main screens, I can start writing" | Full picture or keep driving: entry → success state, the failure path, and every named blocker, all observed live. |
| "Re-run it, it'll probably pass this time" | Read the artifacts first. A phantom remedy is applied once, then escalated — never looped. |
| "It's probably just an 'Allow' prompt, I'll tap it" | System dialogs vary by simulator/OS state; a wrong guess can leave the app or session in an unrecoverable state. Ask the user. |
| "I dismissed the permission prompt while exploring, so the test is fine" | You dismissed it once, by hand. `reset_app_data: always` brings it back on every launch — if the test doesn't dismiss it in setup, the suite is blocked on a fresh simulator even though the flow works. |
| "I'll give the permission alert an accessibility identifier too" | It isn't the app's view. System alerts live outside the app hierarchy and no app-code change can label them — match the visible button label or use the driver's alert API. |
| "Asking about this permission prompt breaks the one-round rule" | The one-round budget is for requirements. A blocker you only discovered by driving the app is an escalation step 3 demands — ask it. |

## Red flags — stop and re-read this file

- Asking the user something `codegraph explore` or the live hierarchy already answers
- Skipping the success / failure / blockers questions, or starting step 3 with no
  `.agentqa/memory/.session-requirement.md` written
- Exploring before `codegraph init` finished and the source was read
- Any Appium call during step 3 — session, MCP `page_source`, or script
- Building the app when `build.policy: human`
- A `.py`/pytest file created before step 7 (exploring should be `agent-device` calls, not a script)
- Writing a test while any part of the flow, its failure path, or a named blocker
  is still unobserved
- Writing a test for a screen you never saw in the live hierarchy
- A Working-layer file (`.run-checkpoint.md`, `.session-requirement.md`) left
  behind after the session ends
- An observation captured with no `#<flow>` tag, or `memory-lint.py` left failing
- A hand-edit to `index.md`, or `index.md` staged for commit
- Dismissing a system permission prompt or pop-up without asking the user first
- A system view observed in step 3 that the test never handles in setup
- Entering the flow through an entry point the user never picked, when step 0
  found more than one
- `git diff` on app code shows deletions
- A password or account name in a committed file
- Fixing a test by loosening its assertion
- Re-running until green without reading the failure artifacts
