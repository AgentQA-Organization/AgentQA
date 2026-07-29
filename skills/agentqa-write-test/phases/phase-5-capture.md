# Phase 5 — Capture durable knowledge

Output: deduped, indexed, linted behavioral memory. The controller owns cleanup.
CLI families: `phase2-wrapper.sh`, `memory-lint-wrapper.sh`, `checkpoint.py`.

1. Review this run's grounded discoveries. Persist only reusable behavioral
   facts: navigation/assertion changes, verified identifiers, system-dialog
   handling, and grounded failure signatures. Do not persist narration,
   unverified product claims, credentials, or a duplicate “completed” note.
2. For every durable observation, run `phase2-wrapper.sh note-propose`, inspect
   all matches, then `note-apply` with ADD, UPDATE, DELETE, or NOOP. Refresh an
   existing line instead of appending a contradiction.
3. Rebuild and lint; non-zero stops the phase:

   ```bash
   <skill_base>/scripts/memory-lint-wrapper.sh .agentqa/memory
   ```

4. Record completion only after lint passes:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check capture_done --evidence "durable observations deduped; memory lint passed"
   python3 <skill_base>/scripts/checkpoint.py complete --path .agentqa/memory/.run-checkpoint.md
   ```

Return to the controller. Do not delete either working-layer file; validation
must still inspect them and `finalize` performs the cleanup.
