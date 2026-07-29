---
name: agentqa-write-test
description: Turn a mobile UI-test idea into a reviewed, passing Appium test on iOS/XCUITest or Android/UiAutomator2, resume after a human build, run existing tests, or diagnose a red test without weakening its assertion. Use when the user asks to write, generate, update, run, debug, or fix an AgentQA/Appium UI test or its behavioral-memory notes.
license: MIT
metadata:
  agentqa-write-test-version: "1.4.0"
---

# AgentQA write test

Run as one sequential agent. Never parallelize phases against the shared device.
Require `.agentqa/config.yml` and `.agentqa/memory/`; otherwise use
`agentqa-init` first. Read host `AGENTS.md` instructions before changing code.

Resolve `<skill_base>` as this skill directory. All bundled scripts are invoked
from there, never from a guessed host-repo `scripts/` path.

## Common invariants

- Live hierarchy outranks memory, source, and product docs—in that order.
- Phase 2 uses only `agent-device`; Appium begins in Phase 3 verification.
- App-code identifier changes are additive only.
- Persistent observation writes use `memory-write.py` through
  `phase2-wrapper.sh`: propose → inspect → apply. Never raw-append a fact.
- Never hand-edit `.run-checkpoint.md`; only `checkpoint.py` mutates it.
- Any non-zero/unexpected CLI result stops the current block with evidence.
- `build_policy: human` means ask, persist the blocker, and end the turn.

## Start or resume

Checkpoint: `.agentqa/memory/.run-checkpoint.md`.

1. Existing checkpoint → run `checkpoint.py status --path <checkpoint>` and
   resume its run id/phase. Never re-clarify or re-explore a resumed phase 3.
2. New-test request → initialize:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py init --path <checkpoint> --mode new --flow <flow>
   ```

3. Explicit red-test diagnosis → verify the named file exists, then initialize:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py init --path <checkpoint> --mode diagnose --test-file <path>
   ```

   Diagnose starts at Phase 4; do not invent evidence for Phases 1–3.
4. Bare “run tests” request with no writing task → ask `pytest-only` or `full
   diagnosis`. Pytest-only runs the requested command and stops without memory
   or checkpoint work. Full diagnosis uses diagnose mode.

## Controller loop

1. Run `checkpoint.py status`. Read `phases/INDEX.md`, then exactly the current
   phase file. Load `references/android.md` only when state platform is Android.
2. Execute the phase. If it sets `WAITING_FOR_USER`, ask once and end the turn.
3. If status is not `COMPLETE`, remain in the same phase. Validation failure
   mechanically reopens that phase; fix only reported gaps and complete again.
4. Validate:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py validate --path <checkpoint>
   ```

   Phase 4 adds `--pytest-ok` only when its latest targeted pytest returned zero
   and the test has not changed since. Never pass it from user assertion.
5. After validation PASS: Phase 1 → `advance`, then
   `set-failures-baseline`; Phases 2–4 → `advance`; Phase 5 → `finalize`.
6. Reload status and only the newly selected phase. Never preload later phases.

For a grounded terminal real failure, Phase 4 captures the signature, reports
it, and calls `abort --reason ...` so no session state leaks into the next run.
