# Phase 2 — Explore live

Output: live-grounded `flows/` and `screens/` notes. CLI families:
`phase2-wrapper.sh`, `agent-device`, `checkpoint.py`.

1. Read the session requirement, current-flow memory slice, and code map.
2. Resolve the app id from config: iOS `bundle_id`, Android `app_package`.
3. Start exploration mechanically:

   ```bash
   <skill_base>/scripts/phase2-wrapper.sh explore --app-id <app_id>
   ```

   The wrapper reads `reset_app_data`, wipes first when required, and opens the
   correct platform. A non-zero result stops the phase.
4. Use only `agent-device snapshot`, `press`, `fill`, and screenshot/coordinates
   where hierarchy is sparse. No Appium, pytest, or test file in this phase.
5. Observe live, end to end: selected entry point, every success waypoint,
   failure behavior, and every named blocker. Cross-check code/docs/memory, but
   live hierarchy wins. If a system-owned dialog appears, show its choices to
   the user and stop; never guess. Resume in this phase after their answer.
6. Create missing note skeletons with valid frontmatter before adding facts.
   Directly creating frontmatter is allowed; observation lines are not.
7. For the flow and every visited screen, run the two-step protocol:

   ```bash
   <skill_base>/scripts/phase2-wrapper.sh note-propose \
     --memory-dir .agentqa/memory --file <flows|screens>/<name>.md \
     --cat <category> --text "<live observation #flow>"
   # Inspect all proposed matches, then choose exactly one:
   <skill_base>/scripts/phase2-wrapper.sh note-apply \
     --memory-dir .agentqa/memory --op <ADD|UPDATE|DELETE|NOOP> \
     <appropriate --file or --target> --cat <category> --text "<observation>"
   ```

   Every observation includes `#<flow>`. Identifier observations use
   `added-unverified <YYYY-MM-DD>`. Do not create a `failures/` note unless a
   real cross-run signature with symptom, cause, and remedy was observed.
8. Rebuild and lint:

   ```bash
   <skill_base>/scripts/phase2-wrapper.sh lint --memory-dir .agentqa/memory
   ```

9. Only after the full live path and lint pass:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check exploration_done --evidence "entry, success, failure, blockers observed live"
   python3 <skill_base>/scripts/checkpoint.py complete --path .agentqa/memory/.run-checkpoint.md
   ```

Return to the controller. Do not validate or advance here.
