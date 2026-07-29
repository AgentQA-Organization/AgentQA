# Phase 3 — Add and verify identifiers

Output: additive app-code identifiers, then live hierarchy verification.

## 3A — Add and build

1. Read current-flow screen notes and source files. Add identifiers only where
   app-owned UI lacks stable locators. Follow config `identifier_convention`.
   iOS: `accessibilityIdentifier`. Android: use the loaded Android reference.
   Never change behavior, layout, validation, or navigation.
2. Record each addition as `added-unverified <YYYY-MM-DD> #<flow>` through
   `phase2-wrapper.sh note-propose`, inspect, then `note-apply`.
3. Run `git diff --numstat -- <app-code paths>`. Any deletion stops the phase.
4. Read checkpoint `build_policy`:
   - `human`: run the command below, ask the user to build/install, then end the
     turn with no more tool calls.
   - `agent`: run the project's one documented platform build/install command.
     Do not set a human blocker.

   ```bash
   python3 <skill_base>/scripts/checkpoint.py set-blocker \
     --path .agentqa/memory/.run-checkpoint.md \
     --blocker WAITING_FOR_HUMAN_BUILD
   ```

## 3B — Verify after the build

1. Pull fresh Appium `page_source` using the available Appium integration. A
   human reply is not build evidence. Grep every new identifier in the fresh
   hierarchy: iOS `name=`, Android `content-desc=`/`resource-id=`.
2. If any identifier is missing, fix only its app-code placement and return to
   3A/build. Do not proceed against a stale binary.
3. For each identifier found live, run `note-propose`, inspect it, then
   `note-apply --op UPDATE --target <file:line>` to replace
   `added-unverified` with `verified-in-hierarchy <YYYY-MM-DD> #<flow>`.
4. If resuming a human blocker, clear it only after all hierarchy evidence is
   present. In agent-build mode no blocker exists, so skip this command:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py clear-blocker \
     --path .agentqa/memory/.run-checkpoint.md
   ```

5. Finish:

   ```bash
   python3 <skill_base>/scripts/checkpoint.py record-check --path .agentqa/memory/.run-checkpoint.md --check identifiers_verified --evidence "all current-flow identifiers found in fresh page_source"
   python3 <skill_base>/scripts/checkpoint.py complete --path .agentqa/memory/.run-checkpoint.md
   ```

Return to the controller. Do not validate or advance here.
