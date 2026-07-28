# Release Notes — since v1.3.1

**27 commits · 2026-07-27 → 2026-07-28**

## Highlights

This release introduces the **AgentQA Studio permission bridge** — Studio can
now surface an agent's permission and system-dialog prompts (tool
confirmations, wrong-typed `cwd`/`connector_id` guards, etc.) as cards in the
mailbox instead of blocking on the terminal, plus a scaffolding script that
seeds a permission allowlist during `agentqa-init`.

It also makes **AgentQA Studio's dashboard launcher cross-platform**. The
boot logic (`bin/agentqa-studio` and the agent's own boot step) was bash-only,
so `/agentqa-studio` silently failed to start its dashboard on native Windows
(PowerShell/cmd.exe) — the port never opened and the browser had nothing to
connect to. A new `studio-launch.py` owns all boot logic behind one
shell-agnostic command, plus a `bin/agentqa-studio.cmd` shim for Windows users
running it directly.

## Added

- **feat(studio): wire the permission bridge to the mailbox** — routes
  permission prompts from the agent into Studio's mailbox as cards.
  ([6a5ce89](https://github.com/AgentQA-Organization/AgentQA/commit/6a5ce89))
- **feat(studio): register the permission bridge as a plugin hook** — hooks
  the bridge into the plugin lifecycle. ([4f53e8d](https://github.com/AgentQA-Organization/AgentQA/commit/4f53e8d))
- **feat(studio): permission-bridge decision helpers** — shared helpers for
  approve/deny decision output. ([05fff6b](https://github.com/AgentQA-Organization/AgentQA/commit/05fff6b))
- **feat(studio): add the permission question subtype and its card label** —
  gives permission prompts their own card type in the UI.
  ([da70f0b](https://github.com/AgentQA-Organization/AgentQA/commit/da70f0b))
- **feat(init): scaffold the AgentQA permission allowlist** — new
  `scaffold-permissions.sh` script (plus tests) run during `agentqa-init`.
  ([7cf6e75](https://github.com/AgentQA-Organization/AgentQA/commit/7cf6e75))
- **feat(studio): add a cross-platform launcher script for the dashboard
  daemon** — new `studio-launch.py` boots the dashboard on native Windows as
  well as bash, behind one shell-agnostic command.
  ([d8735c4](https://github.com/AgentQA-Organization/AgentQA/commit/d8735c4))
- **feat(studio): add a Windows launcher shim, fix the stale PATH-install
  docs** — new `bin/agentqa-studio.cmd` for humans running the dashboard
  directly on Windows. ([9f3d73c](https://github.com/AgentQA-Organization/AgentQA/commit/9f3d73c))

## Fixed

- **fix(studio): restore mailbox state after permission cards, pin the type
  guards** — corrects mailbox state handling once a permission card resolves.
  ([8642cd8](https://github.com/AgentQA-Organization/AgentQA/commit/8642cd8))
- **fix(studio): guard permission bridge against wrong-typed cwd/connector_id**
  — defensive validation on hook input. ([b7951ac](https://github.com/AgentQA-Organization/AgentQA/commit/b7951ac))
- **fix(studio): guard note field against non-string types in decide_output**
  ([fc43de7](https://github.com/AgentQA-Organization/AgentQA/commit/fc43de7))
- **fix(studio): name the system-dialog card by its subtype, not its kind** —
  fixes mislabeled system-dialog cards. ([a220d08](https://github.com/AgentQA-Organization/AgentQA/commit/a220d08))
- **fix(studio): boot the dashboard via a single cross-platform command** —
  SKILL.md's boot step no longer relies on bash-only syntax (`nc -z`, `&`
  backgrounding, a hardcoded `/tmp` log path).
  ([25b3705](https://github.com/AgentQA-Organization/AgentQA/commit/25b3705))
- **fix(studio): close final-review gaps in the Windows launcher** — path
  resolution to the git repo root, the launcher's "always exit 0" guarantee,
  and doc accuracy.
  ([fd03258](https://github.com/AgentQA-Organization/AgentQA/commit/fd03258))
- **fix(studio): close the last exit-0 gap in `resolve_repo()`** — a
  non-UTF-8-encoded repo path could still crash the launcher instead of
  degrading gracefully.
  ([470b2ae](https://github.com/AgentQA-Organization/AgentQA/commit/470b2ae))

## Changed

- **refactor: agent-studio consume too much token** — trims token usage in
  the Studio agent loop. ([a688223](https://github.com/AgentQA-Organization/AgentQA/commit/a688223))
- **chore: move agentqa-write-test eval harness to AgentQA-Workspace** —
  relocates the eval harness out of this repo. ([2c9ac1d](https://github.com/AgentQA-Organization/AgentQA/commit/2c9ac1d))
- **chore: move plan and update skills** — repo housekeeping; also removes
  ~15 superseded planning/design docs from `docs/plans/` and
  `docs/plans/design/` (net −17k lines). ([18915b3](https://github.com/AgentQA-Organization/AgentQA/commit/18915b3))
- **chore: move Studio Windows-launcher plan + spec to AgentQA-Workspace** —
  same housekeeping pattern, applied to this release's own planning docs.
  ([f1e08ac](https://github.com/AgentQA-Organization/AgentQA/commit/f1e08ac))

## Docs

- **docs(studio): document the permission bridge** and **close pre-merge
  review gaps in the permission bridge docs**
  ([5bd8c87](https://github.com/AgentQA-Organization/AgentQA/commit/5bd8c87), [385e3c1](https://github.com/AgentQA-Organization/AgentQA/commit/385e3c1))
- **docs(studio): implementation plan** and **design** for the permission
  bridge ([b88bf4c](https://github.com/AgentQA-Organization/AgentQA/commit/b88bf4c), [cf044a1](https://github.com/AgentQA-Organization/AgentQA/commit/cf044a1))
- **docs(studio): carry the rejection reason via exit 2** — documents the
  exit-code convention for conveying a rejection reason.
  ([b581405](https://github.com/AgentQA-Organization/AgentQA/commit/b581405))

## Stats

194 files changed, 1,594 insertions(+), 17,057 deletions(-) — the drop is
mostly superseded planning docs and the eval harness moved to
AgentQA-Workspace.
