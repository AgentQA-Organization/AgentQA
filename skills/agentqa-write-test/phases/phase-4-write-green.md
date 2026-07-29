# Phase 4 — Write and green loop

Output: a reviewed, passing targeted test.

## Evidence-first diagnosis entry

When checkpoint `mode` is `diagnose`, do not run pytest first. Read the saved
failure XML, then PNG, then recalled `failures/` notes and live `page_source`.
Preserve the original assertion and classify before acting.

## Write block

For a new test, read verified identifiers, flow/screen notes, and the session
requirement. Write page objects and `artifacts.test_file` under configured
`test_dir`. Use identifiers for app-owned UI; visible text only for web/system
UI. Credentials come only from config-named environment variables. Handle every
observed reset-time system dialog in setup. Assert confirmed success and cover
the confirmed failure/edge behavior.

## Green block

1. Load this block only after the test exists:

   ```bash
   python3 <skill_base>/scripts/green-prechecks.py check
   cd <test_dir> && .venv/bin/pytest tests/test_<flow>.py -v --setup-show
   ```

2. A first failure is evidence, not an expected red step. Before any retry read
   artifact XML → PNG → current `page_source`. Classify:
   - locator/test-code drift: fix locally and rerun the targeted file;
   - missing identifier/app-code problem: run `checkpoint.py
     route-to-identifiers --path ...`; return to the controller for Phase 3;
   - known phantom: apply its recorded remedy once; if still red, escalate;
   - real app/backend failure: never weaken, delete, catch, skip, or xfail the
     assertion. Capture a `failures/` signature through `note-propose` →
     `note-apply`, lint memory, report the blocker, then run:

     ```bash
     python3 <skill_base>/scripts/checkpoint.py abort \
       --path .agentqa/memory/.run-checkpoint.md --reason "<grounded real failure>"
     ```

3. No blind retries. Each retry follows a concrete evidence-backed change.
4. When targeted pytest is green, present the app-code diff and test diff to the
   user. Ask for approval. If they request changes, remain in Phase 4.
5. After explicit approval:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check test_approved --evidence "targeted pytest passed; user approved diff"
   python3 <skill_base>/scripts/checkpoint.py complete --path .agentqa/memory/.run-checkpoint.md
   ```

Return the latest targeted pytest success to the controller so it can pass
`--pytest-ok` during validation, but only if the test has not changed since that
run. Do not validate or advance here.
