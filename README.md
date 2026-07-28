# AgentQA — agent-driven mobile UI test automation skills

Three [Agent Skills](https://agentskills.io) that let an AI coding agent **set up,
write, and run Appium UI tests** for a mobile app — **iOS or Android** — by
exploring the *real* running app, adding accessibility identifiers additively,
remembering what it learns, and keeping humans at the build and review checkpoints.

- [`agentqa-init`](skills/agentqa-init/) sets the machine and repo up.
- [`agentqa-write-test`](skills/agentqa-write-test/) does the testing work.
- [`agentqa-studio`](skills/agentqa-studio/) puts a local web dashboard in front of
  it, so a test can be written and its checkpoints answered from the browser.

One flow, two platforms: the same 0–9 flow, checkpoints, and memory model drive
both, selected by a single `platform:` line in the config — iOS on XCUITest,
Android on UiAutomator2. → [`docs/architecture.md`](docs/architecture.md)

## Key features

- **Only `page_source` is truth.** Code reading lies (feature flags, web SSO
  replacing native screens), so the agent drives the actual app before writing a
  test and trusts what Appium reports over what the source suggests.
- **The skills remember.** Everything learned about your app — navigation paths,
  native-vs-web screens, where each identifier lives, flaky-test signatures — is
  saved to `.agentqa/memory/`, so repeat runs get faster instead of starting cold.
- **Additive by construction.** Accessibility identifiers change nothing about
  behavior or layout — `git diff` on app code shows zero deletions.
- **Humans stay at the checkpoints.** You confirm what "pass" means, you build when
  builds are slow or signed, and you approve the diff — nothing else needs you.
- **Project-agnostic.** Everything app-specific lives in `.agentqa/config.yml` in
  *your* repo; credentials are never committed (only the *names* of env vars).

## Requirements

Node.js and Python 3.9+, plus the platform toolchain — iOS needs macOS with Xcode
+ a simulator; Android needs the Android SDK + a JDK. Full list and pinned
versions: [`docs/toolchain.md`](docs/toolchain.md).

## Installation

**Claude Code (preferred)** — register this repo as a plugin marketplace, then
install:

```bash
claude plugin marketplace add https://github.com/TunNguyen-25/AgentQA
claude plugin install agentqa@agentqa
```

**Any other harness** — a one-liner raw-copy installer (run from inside your app
repo):

```bash
curl -fsSL https://raw.githubusercontent.com/TunNguyen-25/AgentQA/main/install.sh | bash
```

Codex/Cursor plugin manifests, `install.sh` flags, the harness matrix, and the
manual clone route are all in **[`docs/installation.md`](docs/installation.md)**.

## Quick start

```text
1.  /agentqa-init setup   # install & validate the toolchain (once per machine)
2.  /agentqa-init init    # configure THIS app repo (once per project)
3.  /agentqa-write-test "log in with a valid account lands on the home tab"
4.  /agentqa-write-test "run the login suite"   # green loop on demand
```

Give it a **concrete assertion**, not just a screen name — see
[`docs/writing-tests.md`](docs/writing-tests.md).

## The three skills

Each skill owns one job and is invoked directly. They share the host repo's
`.agentqa/` directory, not each other's internals.

| Skill | Invoke | What it owns |
|---|---|---|
| **`agentqa-init`** | `/agentqa-init setup` · `/agentqa-init init` | Machine toolchain (install + validate) and per-repo configuration: `.agentqa/config.yml`, the pytest scaffold, and an empty `.agentqa/memory/` store. Once per machine, once per repo. |
| **`agentqa-write-test`** | `/agentqa-write-test <idea>` | Everything at test time: clarify → explore the real app → add identifiers → verify → write → **run until green**. Owns the behavioral-memory schema and scripts; runs inline, no sub-agents. |
| **`agentqa-studio`** | `/agentqa-studio` | A local web dashboard (`http://127.0.0.1:7332/`) plus a connector that attaches a live agent. Runs the `agentqa-write-test` flow unchanged and routes its clarify / build / review checkpoints to browser cards. |

- **`agentqa-write-test`** follows a disciplined lifecycle and a green loop, and
  also runs existing suites. → [`docs/workflow.md`](docs/workflow.md) ·
  [`docs/writing-tests.md`](docs/writing-tests.md)
- **`agentqa-studio`** runs the *same* flow with the three checkpoints as clickable
  cards; the daemon also runs on its own as a read-only viewer. It costs somewhat
  more tokens than the terminal flow. → [`docs/agentqa-studio.md`](docs/agentqa-studio.md)

## Configuration

`/agentqa-init init` writes `.agentqa/config.yml` — the single source of truth for
project facts: platform, app id, test directory, build policy, reset policy,
credential env-var names, identifier convention, and an optional `docs:` intent
layer. Config holds *structured facts*; `.agentqa/memory/` holds *narrative
knowledge*; `CLAUDE.md`/`AGENTS.md` just points at the memory — no duplication.

Field-by-field reference: **[`docs/configuration.md`](docs/configuration.md)**.

## Documentation

| Topic | Doc |
|---|---|
| Design philosophy, the two big ideas, one-flow-two-platforms, trust order | [`docs/architecture.md`](docs/architecture.md) |
| Installing across harnesses, flags, first run, versioning | [`docs/installation.md`](docs/installation.md) |
| The toolchain and requirements | [`docs/toolchain.md`](docs/toolchain.md) |
| The write-test lifecycle: stages, checkpoints, green loop | [`docs/workflow.md`](docs/workflow.md) |
| Writing good tests: the concrete-assertion rule + the 7 discipline rules | [`docs/writing-tests.md`](docs/writing-tests.md) |
| `.agentqa/config.yml` field reference | [`docs/configuration.md`](docs/configuration.md) |
| The memory layer, staleness, capture, and the intent layer | [`docs/memory.md`](docs/memory.md) |
| The behavioral-memory **schema** (single source of truth) | [`memory-model.md`](skills/agentqa-write-test/references/memory-model.md) |
| Platform delta (Android mechanics) | [`android.md`](skills/agentqa-write-test/references/android.md) |
| AgentQA Studio: the dashboard, the mailbox, activation | [`docs/agentqa-studio.md`](docs/agentqa-studio.md) |

## Repository layout

```text
.claude-plugin/           # plugin.json + marketplace.json (Claude Code plugin manifest)
.codex-plugin/            # plugin.json (Codex plugin manifest → ./skills/)
.cursor-plugin/           # plugin.json (Cursor plugin manifest → ./skills/)
.agents/plugins/          # marketplace.json (generic agents-plugin manifest)
skills/
├── agentqa-init/         # setup + init
│   ├── SKILL.md          # router: setup | init → reference file
│   ├── references/       # setup.md, init.md
│   ├── scripts/          # idempotent install/validate scripts (--check mode), harness table,
│   │                     #   install-appium.sh (xcuitest/uiautomator2), install-android-sdk.sh,
│   │                     #   reset-app-data.sh (platform-aware runtime helper, not part of setup)
│   ├── assets/           # config template, test-suite scaffold (platform-dispatched conftest),
│   │                     #   memory scaffold, MCP manifest
│   └── tests/            # scaffold (conftest reset, runbook) tests
├── agentqa-write-test/   # the test-time flow, self-contained
│   ├── SKILL.md          # the 0–9 flow + the green loop (iOS inline, Android delta linked)
│   ├── references/       # clarify.md, memory-model.md (THE store schema), android.md (platform delta)
│   ├── scripts/          # memory_common.py (schema), memory-write.py, memory-index.py, memory-lint.py
│   └── tests/            # memory store tests
└── agentqa-studio/       # the browser connector (transport adapter over agentqa-write-test)
    ├── SKILL.md          # attach → watch mailbox → run write-test → route checkpoints to cards
    ├── references/       # requirements-doc.md (uploaded spec), troubleshooting.md — read on demand
    ├── scripts/          # studio_common.py (protocol), studio-attach/-wait/-post/-detach.py
    └── tests/            # protocol + script tests (validated against studio/protocol_v1.json)
docs/                     # the documentation this README links to
studio/                   # AgentQA Studio daemon (M1 viewer + M2 mailbox): stdlib http.server + vanilla-JS UI
hooks/                    # plugin hooks: PermissionRequest -> Studio permission card
install.sh                # the cross-harness installer (raw-copy, for harnesses without marketplace support)
```

## Versioning

Releases are git-tagged with SemVer (`v1.3.1`); pin the installer with
`--ref v<x.y.z>`. Details in [`docs/installation.md`](docs/installation.md#versioning).

## License

MIT — see [`LICENSE`](LICENSE).
