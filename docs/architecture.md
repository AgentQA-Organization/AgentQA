# Architecture & design philosophy

Why AgentQA is built the way it is. This is the "why" behind the mechanics; the
"how" of a run lives in [`workflow.md`](workflow.md).

## The two ideas that make it work

**1. Only `page_source` is truth.** Reading source code lies — a feature flag can
hide a screen, a build can replace a native login with web SSO — so the agent
drives the *actual* running app before writing a test and trusts what Appium
reports (`page_source`, the live view hierarchy) over what the source suggests.
The source is a white-box hint, never the last word.

**2. The skills remember.** Everything learned about your app — navigation paths,
which screens are native vs. web, where each accessibility identifier lives,
flaky-test signatures — is saved to `.agentqa/memory/` so repeat runs get faster
and more reliable instead of starting cold. This is knowledge the agent
hand-earns at runtime that source code can't tell you. See [`memory.md`](memory.md).

## Project-agnostic by design

Nothing app-specific is ever hardcoded in a test. Everything that varies between
apps — platform, app id, test directory, build policy, credential env-var names,
identifier convention — lives in `.agentqa/config.yml` inside *your* repo, created
by `/agentqa-init init`. Credentials are never committed (only the *names* of the
env vars the tests read). See [`configuration.md`](configuration.md).

## One flow, two platforms

The same 0–9 flow, the same human checkpoints, and the same memory model drive
**both iOS and Android**, selected by a single `platform:` line in the config:

| | iOS | Android |
|---|---|---|
| Appium driver | XCUITest (WebDriverAgent) | UiAutomator2 |
| Device tooling | `simctl` | `adb` |
| Identifier mechanism | `accessibilityIdentifier` | `contentDescription` / `resource-id` |

The logical identifier convention (`screen_element_type`) is shared; only the
mechanism differs. The platform-specific mechanics are documented once, in
[`skills/agentqa-write-test/references/android.md`](../skills/agentqa-write-test/references/android.md).

## Trust order

When sources disagree, the ranking is fixed:

> **live app > memory > source code > docs**

The live hierarchy is strongest because it's the only thing that can't be wrong
about itself. A product doc is weakest because it describes *intent*, which can be
months out of date — which is exactly why intent (the optional `docs:` layer)
ranks below even the source code the skill already treats as unreliable. This
ordering is applied during recall and during the optional intent layer; see
[`memory.md`](memory.md).

## Everything is a file

There is no database, no long-running memory server, no link graph. Behavioral
memory is plain Markdown plus three small stdlib scripts. AgentQA Studio's agent
bridge is a file "mailbox." Config is a YAML file. This "everything is a file"
ethos means the whole system is greppable, diffable, and committable — you can
read and prune any of it by hand.

## No sub-agents

Everything runs inline in the main agent's own context — exploring the real app
with `agent-device`, diagnosing a failure (parsing `page_source` XML, matching it
against the `failures/` library, recommending a fix), and writing or refreshing
memory. There is no fan-out to sub-agents, so nothing is lost across an agent
boundary and the whole run is inspectable in one transcript.

## How the pieces fit

- **Three skills**, each owning one job, sharing the host repo's `.agentqa/`
  directory rather than each other's internals — see the skills table in the
  [README](../README.md).
- **`.agentqa/`** in your repo holds the config, the pytest suite, and the memory
  store. It is the contract between the skills.
- **The toolchain** (Appium, `agent-device`, CodeGraph, the Appium MCP, a Python
  venv) is what the skills drive — each optional-with-a-fallback. See
  [`toolchain.md`](toolchain.md).

## See also

- [`workflow.md`](workflow.md) — the write-test lifecycle this philosophy produces
- [`memory.md`](memory.md) — the memory layer and the intent layer
- [`writing-tests.md`](writing-tests.md) — the rules that keep generated tests trustworthy
- [`toolchain.md`](toolchain.md) — the tools and why each is used
