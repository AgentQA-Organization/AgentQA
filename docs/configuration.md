# Configuration

`/agentqa-init init` writes `.agentqa/config.yml` at your repo root. It is the
single source of truth for **project facts** — everything app-specific, so nothing
is ever hardcoded in a test. This is the user-facing reference; the skill's own
operational notes are in
[`skills/agentqa-init/references/init.md`](../skills/agentqa-init/references/init.md).

## Fields

- **platform** — `ios` or `android`. Selects the driver, device tooling, reset
  mechanism, and identifier strategy. See [`architecture.md`](architecture.md#one-flow-two-platforms).
- **app id** — iOS `bundle_id`, or Android `app_package` + `app_activity`.
- **test directory** — default `AutomationTests`.
- **build policy** — `human` (agent hands off building) or `agent` (agent builds).
  Drives the **Build** checkpoint in [`workflow.md`](workflow.md).
- **reset policy** — `reset_app_data: always` (default) wipes the app's local data
  before every launch, so each test run and each exploration starts clean; `never`
  keeps state between launches. iOS clears the data container + privacy grants;
  Android runs `adb shell pm clear` (data + cache + revoked permissions). Either
  way the app is **never uninstalled** (a human-installed build survives) and the
  shared keychain/keystore isn't wiped.
- **credential env-var names** — the tests read credentials from these env vars.
  Values are **never stored** — only the names. Never hardcoded, never committed.
- **identifier convention** — recommended `screen_element_type` (e.g.
  `login_phone_field`, `home_profile_button`). The logical convention is shared
  across platforms; the mechanism is per-platform (iOS `accessibilityIdentifier`,
  Android `contentDescription` / `resource-id`).
- **`docs:` — product artifacts** *(optional)* — local paths/globs to SRDs, PM
  scenarios, user flows, or acceptance criteria your team already wrote. This
  enables the **intent layer**: `agentqa-write-test` reads them to pre-fill its
  clarify round and aim its exploration. They are treated as *intent, not truth* —
  see the intent layer in [`memory.md`](memory.md#the-intent-layer-optional). Omit
  the block entirely if you have none; everything works exactly as before, and the
  skill never asks you for one.

## Config vs. memory vs. CLAUDE.md

Three stores, no duplication:

| Store | Holds | Example |
|---|---|---|
| `.agentqa/config.yml` | **structured facts** | platform, app id, build policy |
| `.agentqa/memory/` | **narrative knowledge** | "login is native, terms is a web view" |
| `CLAUDE.md` / `AGENTS.md` | a **pointer** to the memory | one line, nothing more |

Facts are never duplicated across them. See [`memory.md`](memory.md) for the
narrative-knowledge store.

## See also

- [`installation.md`](installation.md) — running `/agentqa-init init` in the first place
- [`writing-tests.md`](writing-tests.md) — how the identifier convention and credential vars are used
- [`memory.md`](memory.md) — narrative knowledge and the intent layer
