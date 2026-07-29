# Phase 1 — Map and clarify

Output: `.agentqa/memory/.session-requirement.md` plus the checkpoint code map.
CLI families: `codegraph`, `memory-index.py`, `checkpoint.py`.

1. Run `codegraph init`, then `codegraph explore "<flow screens and symbols>"`.
   Read every source file used to establish entry points, screens, navigation,
   validation, and blast radius. CodeGraph output is a map, not live truth.
2. If `.agentqa/config.yml` has `docs:`, read only matching product-artifact
   sections. Treat them as intent to confirm, never as hierarchy evidence.
3. Rebuild and read the current-flow memory slice:

   ```bash
   python3 <skill_base>/scripts/memory-index.py .agentqa/memory
   python3 <skill_base>/scripts/memory-index.py .agentqa/memory --flow <flow>
   python3 <skill_base>/scripts/memory-index.py .agentqa/memory --stale
   ```

4. Read `../references/clarify.md`. Ask one batched requirement round containing
   success, failure, and blockers. If code shows multiple entry points, list
   them and ask which one. Confirm product-doc claims instead of asking cold.
   Never ask questions answerable by source or the live hierarchy.
5. Write `.agentqa/memory/.session-requirement.md` with frontmatter and these
   non-empty sections: `## Request`, `## Success`, `## Failure`, `## Blockers`,
   `## Environment / preconditions`. Unverified product claims remain here.
6. Record the code map using real comma-separated values, including source files:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-code-map \
     --path .agentqa/memory/.run-checkpoint.md \
     --entry-points <entry1,entry2> --screens <screen1,screen2> \
     --source-files <file1,file2>
   ```

7. Record each check only after its evidence exists:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check codegraph_indexed --evidence "<queries/results>"
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check source_read --evidence "<files read>"
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check clarification_done --evidence "<confirmed assertion>"
   python3 <skill_base>/scripts/checkpoint.py complete --path .agentqa/memory/.run-checkpoint.md
   ```

Return to the controller. Do not validate or advance here.
