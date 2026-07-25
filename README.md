# AgentQA — agent-driven mobile UI test automation skills

Three [Agent Skills](https://agentskills.io) that let an AI coding agent **set up,
write, and run Appium UI tests** for a mobile app — **iOS or Android** — by
exploring the *real* running app, adding accessibility identifiers additively,
remembering what it learns, and keeping humans at the build and review
checkpoints. [`agentqa-init`](skills/agentqa-init/) sets the machine and repo up,
[`agentqa-write-test`](skills/agentqa-write-test/) does the testing work, and
[`agentqa-studio`](skills/agentqa-studio/) puts a local web dashboard in front of
it so a test can be written and its checkpoints answered from the browser.

One flow, two platforms: the same 0–9 flow, checkpoints, and memory model drive
both, selected by a single `platform:` line in the config. iOS runs on the
XCUITest driver (`simctl`, `accessibilityIdentifier`); Android on the UiAutomator2
driver (`adb`, `contentDescription`/`resource-id`). The platform-specific
mechanics live in [`references/android.md`](skills/agentqa-write-test/references/android.md).

Two ideas make it work:

- **Only `page_source` is truth.** Code reading lies (feature flags, web SSO
  replacing native screens), so the agent drives the actual app before writing a
  test and trusts what Appium reports over what the source suggests.
- **The skills remember.** Everything learned about your app — navigation paths,
  which screens are native vs. web, where each identifier lives, flaky-test
  signatures — is saved to `.agentqa/memory/` so repeat runs get faster and more
  reliable instead of starting cold.

Project-agnostic by design: everything app-specific (platform, app id, test dir,
build policy, credential env-var names, identifier convention) lives in
`.agentqa/config.yml` inside *your* repo, created by `/agentqa-init init`. Nothing
app-specific is ever hardcoded in a test, and credentials are never committed.

**Requirements:** Node.js and Python 3.9+, plus the platform toolchain — iOS
needs macOS with Xcode + an iOS simulator; Android needs the Android SDK (`adb`,
an emulator or device) + a JDK (macOS or Linux). Pinned tool versions live in
[`scripts/common.sh`](skills/agentqa-init/scripts/common.sh).

---

## Install

**Claude Code (preferred):** register this repo as a plugin marketplace, then
install — `agentqa-init`, `agentqa-write-test`, and `agentqa-studio` are
auto-discovered from [`skills/`](skills/) via the
[`.claude-plugin/`](.claude-plugin/) manifest:

```bash
claude plugin marketplace add https://github.com/TunNguyen-25/AgentQA
claude plugin install agentqa@agentqa
```

Default scope is `user` (this machine only); add `--scope project` to commit the
choice to `.claude/settings.json` and share it with your team. Update with
`claude plugin update agentqa@agentqa`; remove with `claude plugin uninstall
agentqa@agentqa`.

**Codex / Cursor (plugin manifest):** the repo also ships per-harness plugin
manifests that point at the same [`skills/`](skills/) folder —
[`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and
[`.cursor-plugin/plugin.json`](.cursor-plugin/plugin.json) (the same convention as
[`.claude-plugin/`](.claude-plugin/), mirroring
[obra/superpowers](https://github.com/obra/superpowers)). Install the repo through
the harness's own plugin flow, or use `install.sh` below — for Codex it raw-copies
the skills into `.agents/skills/`, the Agent-Skills path Codex reads.

**Other harnesses (or no `claude`/plugin flow) — `install.sh`:** a raw-copy
installer that places the skill folders directly into your harness's skills
directory.

**One-liner** (run from inside your app repo — installs into `.claude/skills/`):

```bash
curl -fsSL https://raw.githubusercontent.com/TunNguyen-25/AgentQA/main/install.sh | bash
```

To pass flags through the pipe, use `bash -s --`, e.g. `curl -fsSL <url> | bash -s -- --global`.

**Manual** (inspect first):

```bash
git clone https://github.com/TunNguyen-25/AgentQA.git
cd AgentQA && ./install.sh
```

The installer detects your harness and copies both skill folders into that
harness's skills directory. Flags:

| Flag | Effect |
|---|---|
| _(default)_ | install into the current app repo (`<repo>/.claude/skills/`) |
| `--global` | install user-wide (`~/.claude/skills/`) |
| `--ref <tag\|branch>` | version to fetch when cloning (default `main`) |
| `--harness <id>` | override harness detection (or set `AGENTQA_HARNESS`) |
| `--setup` | also run the toolchain setup after installing (default: no) |

**Harness support:** Claude Code installs via the native marketplace or
`install.sh`. Codex and Cursor have per-harness plugin manifests
(`.codex-plugin/`, `.cursor-plugin/`) pointing at the shared `skills/`, and Codex
is also a native `install.sh --harness codex` target (raw-copy into
`.agents/skills/`). For any other harness, `install.sh` prints where to place the
`agentqa-init/`, `agentqa-write-test/`, and `agentqa-studio/` folders. Because every skill is plain
[Agent Skills](https://agentskills.io) `SKILL.md`, the same `skills/` works across
harnesses — only the install path differs. Per-harness plugin marketplaces are
still maturing, so `install.sh` stays the guaranteed path.

### First run

```text
1.  /agentqa-init setup   # install & validate the toolchain (once per machine)
2.  /agentqa-init init    # configure THIS app repo (once per project)
3.  /agentqa-write-test "log in with a valid account lands on the home tab"
4.  /agentqa-write-test "run the login suite"   # green loop on demand
```

---

## The three skills

Each skill owns one job and is invoked directly. They share the host repo's
`.agentqa/` directory, not each other's internals.

| Skill | Invoke | What it owns |
|---|---|---|
| **`agentqa-init`** | `/agentqa-init setup` · `/agentqa-init init` | Machine toolchain (install + validate) and per-repo configuration: `.agentqa/config.yml`, the pytest scaffold, and an empty `.agentqa/memory/` store. Run once per machine, once per repo. |
| **`agentqa-write-test`** | `/agentqa-write-test <idea>` | Everything at test time: clarify → explore the real app → add identifiers → verify → write → **run until green**. Owns the behavioral-memory schema and the memory scripts; runs everything inline, no sub-agents. |
| **`agentqa-studio`** | `/agentqa-studio` | AgentQA Studio: a local web dashboard (the repo-root `studio/` daemon) plus a connector that attaches a live agent to it. Runs the `agentqa-write-test` flow unchanged and routes its clarify / build / review checkpoints to browser cards. |

`agentqa-init` has two subcommands — `setup` (alias `install`) and `init` (alias
`config`); `agentqa-write-test` takes free-text arguments; `agentqa-studio` takes
none — invoke it to attach and drive test-writing from the dashboard.

### `/agentqa-write-test <idea>`

```text
/agentqa-write-test "log in with a valid account lands on the home tab"
```

Give it a concrete assertion, not just a screen name — "logging in with a
**valid** account lands on the home tab" tells the agent what "pass" means; "test
login" does not. See [Writing good tests](#writing-good-tests).

Running an existing suite is part of this skill's green loop: ask it to run the
tests and it offers **pytest-only (lean)** — just the pytest output — or **full
diagnosis**, which recalls the `failures/` library, diagnoses a failure inline
from the saved artifacts, and captures new signatures.

---

## The toolchain

`/agentqa-init setup` installs and validates these. Each is optional-with-a-fallback,
so the skills still work (with less automation) when one is missing.

| Tool | What it is | Why the skills use it |
|---|---|---|
| **Appium 2.x + the platform driver** | The mobile automation server + the driver for your platform: **XCUITest** for iOS (WebDriverAgent under the hood) or **UiAutomator2** for Android (`adb`). `setup` installs whichever the platform scope needs. | The actual engine your generated pytest tests drive the app through, and the source of `page_source` — the one source of truth. |
| **agent-device** | A cross-platform CLI that is the agent's "hands" on the device (`open`, `snapshot -i`, `press`/`fill --settle`, `screenshot`) — drives iOS simulators and Android emulators/devices alike. | Lets the agent **explore the real app** before writing a test — walking the flow, reading the live view hierarchy, and seeing what actually renders (native vs. web). |
| **CodeGraph** | A codebase index + query MCP (call chains, blast radius). |  Helps the agent map a flow to the screens/symbols in your source and see what a change touches — *before* it edits, so identifier additions stay surgical. |
| **Appium MCP** (`appium-mcp`) | An MCP server that talks to a running Appium session. | First-class `page_source` and identifier-verification reads while writing/diagnosing a test, instead of shelling out. |
| **Python venv + pytest** | The test harness (`conftest.py` fixture auto-attaches to the booted device — simulator or emulator — saves `page_source` + a screenshot on any failure, and writes a per-run execution runbook + final screenshot to `artifacts/runbook/` on pass or fail). | Runs the tests and captures failure evidence for diagnosis. |

MCP servers (`codegraph`, `appium`) are defined once in a portable
`.agentqa/mcp.json`; on Claude Code they auto-register, and on other harnesses
setup prints where to import them. Behavioral memory needs no server of its own —
it's plain Markdown plus three small stdlib scripts. **Never run a CPU-heavy job (e.g. re-indexing
CodeGraph) while device tests are running** — on iOS WebDriverAgent waits time
out, and on Android a busy host slows the UiAutomator2 server; both surface as
phantom failures.

---

## How the agent remembers

`agentqa-write-test` keeps a **behavioral memory** of your app in `.agentqa/memory/` at your
repo root — committed and team-shared, and containing **no secrets** (only the
*names* of credential env vars). This is knowledge the agent hand-earns at runtime
and that source code can't tell you; CodeGraph already regenerates the code-level
knowledge separately.

Notes are plain Markdown — frontmatter plus one fact per line
(`- [category] fact #flow`). No database, no server, no link graph: the `#flow`
tag is what ties a screen or a failure to the flows it belongs to.

| Folder / file | One note per | Captures |
|---|---|---|
| `flows/` | user flow | navigation path, **the assertion that matters**, edge cases, which steps are native vs. web |
| `screens/` | screen | native-or-web, the **identifier map** (logical name → where it's set + when it was last verified), quirks (e.g. "submit button sits under the keyboard") |
| `failures/` | phantom/flaky signature | symptom → cause → remedy; a shared library across flows |
| `env.md` | (single file) | build-policy rationale, credential env-var names, device/simulator gotchas |
| `index.md` | (generated) | compact view rebuilt from the notes — **gitignored**, never hand-edited |
| `.session-requirement.md` | (ephemeral, per session) | Working layer — what you asked for this session: success criteria, failure criteria, blockers; gitignored, deleted when the session ends |
| `.run-checkpoint.md` | (ephemeral, per run) | Working layer — the in-flight run's state across the build pause; gitignored, deleted on Capture |

The lifecycle is four verbs: **Recall** (load what this flow needs before acting) →
**Verify-on-read** (treat memory as a *claim* and re-check it against live
`page_source`, never blindly trust it) → **Capture** (write deduped observations
when done) → **Refresh** (update a note when reality has changed, rather than
appending a contradiction). On a repeat `/agentqa-write-test`, the agent uses the
flow note as a **map** and only deep-dives where the app diverges from memory —
fast, but still grounded in the live app.

**Recall is scoped to the flow, so a mature store costs no more than a young one.**
`memory-index.py --flow login` returns the login notes and the (deliberately
unscoped) failure library, not all two hundred screens you've ever explored.

**Staleness is computed, not declared.** Every verified identifier carries the date
it was last seen in the hierarchy; `memory-index.py --stale` lists the ones past 30
days with the exact `file:line` to refresh, so re-verification is a task rather than
a warning label.

**Capture goes through `memory-write.py`**, which shows the closest existing
observations and makes the agent choose `ADD`/`UPDATE`/`DELETE`/`NOOP` before
anything is written. The ranking is textual — it catches restatements and misses
the same fact worded differently — so it's a forcing function to look, not a
guarantee. The script also refuses writes that would corrupt the store: paths
outside `flows/`/`screens/`/`failures/`/`env.md`, unknown categories, malformed
identifier lines, and anything shaped like a committed credential. `memory-lint.py`
runs the same checks across the whole store (and `/agentqa-init init --check`
runs it for you).

**No sub-agents.** Everything — exploring the real app with `agent-device`,
diagnosing a failure (parsing `page_source` XML, matching it against the
`failures/` library, recommending a fix), writing/refreshing memory — runs
inline in the main agent's own context.

The store is plain Markdown; read, grep, and prune it directly.

- **[`docs/memory.md`](docs/memory.md)** — how the layers fit together and how
  recall works, in plain terms. Start here.
- **[`memory-model.md`](skills/agentqa-write-test/references/memory-model.md)** —
  the schema. It has exactly one home; every other document points there instead
  of repeating it.

### The intent layer (optional)

Most of what a test needs is discoverable: the code says how navigation works, the
live app says what's on screen. The one thing neither can tell you is **what should
count as passing** — which is why the skill asks about success, failure, and
blockers on every run.

Teams often already answered that, in an SRD, a PM scenario, a user-flow doc. Point
`docs:` in `.agentqa/config.yml` at those files (local paths/globs) and
`agentqa-write-test` will read them to **pre-fill its clarify round** — proposing
"the spec says success is landing on the home tab bar; still right?" instead of
asking you to retype what you already wrote — and to **aim its exploration**.

They are **intent, not truth**, and that distinction is the whole design:

- A spec describes what the app was *meant* to do. It goes stale, it gets
  overtaken by a build. So it ranks *below* the source code, which the skill
  already treats as unreliable. Trust order: **live hierarchy > memory > code > docs.**
- Docs **never skip a clarify question** — they change its form from blank to
  confirm-or-correct. You still decide what the test must prove.
- A claim read from a doc but never seen live stays in the session's scratch file
  and **is deleted with it**. It never enters `flows/`/`screens/`, because that
  store is what later runs trust as a map.
- When a doc and the build disagree, the build wins — and the skill **tells you
  about the gap**, which is often the more useful finding.
- The skill only ever **reads** these files.

No `docs:` block is the normal case, and the skill never asks you for one.

---

## Writing good tests

`/agentqa-write-test <idea>` follows a disciplined flow — the checkpoints and
rules below are what keep the generated tests trustworthy.

1. **Map to code, then nail the assertion.** When a CodeGraph index exists, the
   agent grounds itself in the flow's screen graph *first*, then asks you the one
   thing neither the code nor the app can answer — **what is the expected user
   outcome?** — and pins it as a one-sentence assertion. Everything else
   (screens, fields, validations, navigation, APIs) it discovers itself: source
   code as the white-box tool, the running app as the black-box one. No
   open-ended brainstorming, one batched round of questions.
2. **Recall, then explore the real app.** It loads what memory already knows about
   *this flow*, then drives the flow with agent-device and reconciles against live `page_source` —
   because a real build can replace native login with web SSO, and only the live
   hierarchy is truth.
3. **Identifiers are added additively.** Accessibility identifiers follow your
   config's convention and change **nothing** about behavior, layout, or logic —
   `git diff` on app code must show **zero deletions**.
4. **You build; the agent verifies.** Under `build.policy: human` the agent stops
   and asks you to build & install onto the booted device (right when CLI builds
   are slow or signing is involved — common on iOS), then pulls `page_source` and
   confirms every new identifier actually shows up before writing locators
   against it.
5. **Locators, honestly.** Your identifiers for app-owned UI; visible-label
   predicates only for UI you don't own (web views). Credentials come only from the
   env vars named in the config — never hardcoded, never committed.
6. **Green, then reviewed.** The agent runs until the test passes (its green loop:
   preconditions → pytest → diagnose from the saved artifacts), then shows you the
   additions-only app-code diff and the test for approval.
7. **Never loosen an assertion to make a test pass.** A failing test that reflects a
   real bug is a finding, not something to weaken.

For flaky runs, the `failures/` memory means a known phantom (e.g. stale app state
from an aborted run) is recognized and its remedy applied once automatically, then
escalated if it doesn't clear — rather than re-diagnosed from scratch every time.

---

## Configuration

`/agentqa-init init` writes `.agentqa/config.yml` at your repo root. It is the single
source of truth for project facts:

- **platform** — `ios` or `android` (selects the driver, device tooling, reset
  mechanism, and identifier strategy)
- **app id** — iOS `bundle_id`, or Android `app_package` + `app_activity`
- **test directory** (default `AutomationTests`)
- **build policy** — `human` (agent hands off building) or `agent` (agent builds)
- **reset policy** — `reset_app_data: always` (default) wipes the app's local data
  before every launch, so each test run and each exploration starts clean; `never`
  keeps state between launches. iOS clears the data container + privacy grants;
  Android runs `adb shell pm clear` (data + cache + revoked permissions). Either
  way the app is never uninstalled (a human-installed build survives) and the
  shared keychain/keystore isn't wiped.
- **credential env-var names** the tests read (values are never stored — only names)
- **identifier convention** (recommended: `screen_element_type`, e.g.
  `login_phone_field`, `home_profile_button`) — the logical convention is shared;
  the mechanism is per-platform (iOS `accessibilityIdentifier`, Android
  `contentDescription`/`resource-id`)
- **`docs:` — product artifacts** *(optional)* — local paths/globs to SRDs, PM
  scenarios, user flows, acceptance criteria your team already wrote. See
  [the intent layer](#the-intent-layer-optional) below. Omit it entirely if you
  have none; everything works exactly as before.

Config holds *structured facts*; `.agentqa/memory/` holds *narrative knowledge*;
your `CLAUDE.md`/`AGENTS.md` just points at the memory. Facts are never duplicated
across them.

---

## Layout

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
    ├── scripts/          # studio_common.py (protocol), studio-attach/-wait/-post/-detach.py
    └── tests/            # protocol + script tests (validated against studio/protocol_v1.json)
studio/                   # AgentQA Studio daemon (M1 viewer + M2 mailbox): stdlib http.server + vanilla-JS UI
agentqa-write-test-workspace/  # eval harness: mock app repo, PATH shims, graders (dev-only)
install.sh                # the cross-harness installer (raw-copy, for harnesses without marketplace support)
```

## Versioning

Releases are git-tagged with SemVer (`v1.0.0`). The plugin version lives in
[`.claude-plugin/plugin.json`](.claude-plugin/plugin.json), and each skill carries
its own in its `SKILL.md` frontmatter (`metadata.agentqa-init-version`,
`metadata.agentqa-write-test-version`, `metadata.agentqa-studio-version`). Pin the installer to a release with
`--ref v<x.y.z>`.

## License

MIT — see [`LICENSE`](LICENSE).
