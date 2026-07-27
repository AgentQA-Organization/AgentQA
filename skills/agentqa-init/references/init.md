# /agentqa-init init — configure a project for agent-driven UI testing

Goal: a `.agentqa/config.yml` at the host repo root plus a runnable (empty)
test suite. Idempotent — if pieces exist, keep them and fill only the gaps.

## 1. Gather the facts (ask the user; don't guess)

- **Platform**: `ios` or `android`. If unsure, infer from the repo (an
  `.xcodeproj`/`Package.swift` → iOS; a `build.gradle`/`AndroidManifest.xml` →
  Android) and confirm. It selects the driver, device tooling, reset mechanism,
  and identifier strategy — everything below branches on it.
- **App under test:**
  - iOS → **bundle id** (list installed apps on a booted simulator:
    `xcrun simctl listapps booted`).
  - Android → **app package** + **launcher activity**. List packages with
    `adb shell pm list packages`; resolve the activity with
    `adb shell cmd package resolve-activity --brief <package> | tail -1`. Leave
    `bundle_id` blank and set `app_package`/`app_activity` instead.
- **Test directory** name (default `AutomationTests`).
- **Build policy**: `human` (agent stops and asks the user to build & install
  — right choice when CLI builds are slow or signing is involved, common on iOS)
  or `agent` (often fine for an Android debug APK: `./gradlew installDebug`).
- **Reset local app data on every launch?** `always` (**default** — recommend it;
  every test session and every explore launch starts clean, so runs are
  deterministic and one test can't inherit another's state) or `never` (keep
  state between launches — pick it only when re-establishing state is expensive,
  e.g. a manual login the tests can't redo). The mechanism follows the platform:
  iOS wipes the data container + privacy grants; Android runs
  `adb shell pm clear` (data + cache + revoked runtime permissions). Either way
  the **binary is never uninstalled** (a human-installed build survives) and the
  shared keychain / keystore is not wiped.
- **Credential env var names** the tests will read (e.g. `APP_TEST_USERNAME`).
  Values are never stored anywhere — only the names.
- **Identifier convention** (recommend `screen_element_type`, lowercase
  snake_case: `login_phone_field`, `home_profile_button`; suffixes `field`,
  `button`, `label`, `alert`, `tab`, `cell`). The logical convention is shared
  across platforms; the **mechanism** differs (iOS `accessibilityIdentifier`;
  Android `contentDescription` or a `testTag` exposed as `resource-id`) and is
  the `agentqa-write-test` skill's job — see its `references/android.md`.
- **Product artifacts (optional).** SRDs, PM scenarios, user flows, acceptance
  criteria the team already wrote. `agentqa-write-test` reads them to pre-fill its
  clarify round and aim exploration — they describe *intent*, which is the one
  thing neither the code nor the live app can supply. **Detect, don't
  interrogate:** glob the usual homes (`docs/`, `doc/`, `documentation/`,
  `specs/`, and root files like `PRODUCT.md`, `SPEC.md`, `REQUIREMENTS.md`), show
  the user what you found, and let them confirm, narrow, or add paths. Found
  nothing? Leave the `docs:` block commented out and move on without dwelling —
  plenty of teams keep no such docs, or keep them somewhere the agent can't read,
  and the skill is fully functional without them. Never block init on this, and
  never record a path that isn't a local file or glob.

## 2. Write the config

Copy [assets/config.template.yml](../assets/config.template.yml) to
`.agentqa/config.yml` in the repo root and fill in the answers.

## 3. Scaffold the test suite (if the test dir doesn't exist)

Copy the files from [assets/scaffold/](../assets/scaffold/) into the test
directory:

- `conftest.py` — Appium driver fixture, platform-dispatched on `platform:`:
  iOS uses the XCUITest driver + a booted simulator (bundle id from the config or
  `AGENTQA_BUNDLE_ID`); Android uses the UiAutomator2 driver + a connected
  device/emulator (`app_package`/`app_activity` from the config or
  `AGENTQA_APP_PACKAGE`/`AGENTQA_APP_ACTIVITY`, `ANDROID_SERIAL` to pick among
  several). It attaches with `noReset`, wipes app data when `reset_app_data` is
  `always` (config, or `AGENTQA_RESET_APP_DATA` to override per run) — a `simctl`
  container wipe on iOS, `adb shell pm clear` on Android — cold-starts the app,
  and saves page_source + a screenshot automatically on any test failure.
- `requirements.txt`, `pytest.ini`, `.gitignore` — pinned deps, defaults.
- Create empty `pages/` (+ `__init__.py`), `tests/`, `notes/` directories.

Then create the venv: `scripts/setup-python-env.sh` (from this skill).

**Re-running `init` on a repo scaffolded by an older version:** keep the project's
own files, but fill the gaps — add any missing key to `.agentqa/config.yml`
(`reset_app_data` first; without it the default `always` still applies) and diff
the scaffold's `conftest.py` against the project's. It is generated, not
hand-edited: if the project hasn't customized it, re-copy it so the reset policy
takes effect; if it has, port the change and say what you moved.

## 4. Bootstrap the memory store

Create `.agentqa/memory/` (behavioral knowledge; the note schema lives in the
`agentqa-write-test` skill's `references/memory-model.md` — you don't need it
here, `init` only creates the empty store) by running the scaffold script from
this skill:

```bash
scripts/scaffold-memory.sh            # from the host repo root
```

It creates `flows/`, `screens/`, `failures/`, seeds `env.md` + a fallback
`README.md`, and gitignores `index.md` (that file is generated from the notes by
`agentqa-write-test`'s `memory-index.py`, so committing it only produces merge
conflicts on a file nobody edits). Re-running on a store from an older version
adds the ignore line and, if `index.md` was already committed, prints the one-time
`git rm --cached` to untrack it. The store **starts empty** — `/agentqa-write-test` fills `screens/` with
runtime-verified facts as flows are actually explored, so every note is grounded
in `page_source`. Never pre-seed `screens/` from the CodeGraph index: those
claims are unverified and a real build can contradict them (feature flags, web
SSO replacing native screens).

Then fill `env.md`'s placeholders from the config: the build-policy rationale and
the credential env-var **names** (names only, never values). Add a short pointer
in the repo's agent docs (`CLAUDE.md`/`AGENTS.md`) to `.agentqa/memory/` — the
memory is the home for narrative knowledge; `config.yml` stays the home for
structured facts. Do not duplicate facts across the two.

## 5. Scaffold the permission allowlist

AgentQA writes to `.agentqa/` and the test dir on every run. Without an allowlist
each of those writes raises a permission dialog in the terminal — invisible to
anyone driving the run from the Studio dashboard. Add the rules with:

```bash
scripts/scaffold-permissions.sh            # from the host repo root
```

It merges into any existing `.claude/settings.json` and is safe to re-run.
Writes outside those two areas still ask, which is the point: during a Studio
session they become a card in the browser.

## 6. Reset policy outside pytest

`conftest.py` handles pytest runs. Launches that don't go through pytest — the
`agent-device open` calls `/agentqa-write-test` makes while exploring — reset via
the same mechanism, this skill's `scripts/reset-app-data.sh`:

```bash
scripts/reset-app-data.sh          # platform + app id from .agentqa/config.yml
```

It reads `platform:` from the config and does the right thing: on iOS it
terminates the app, empties its data container (`Documents/`, `Library/`
including NSUserDefaults, `tmp/`) and resets its privacy grants; on Android it
runs `adb shell pm clear <app_package>` (data + cache + revoked runtime
permissions). Neither uninstalls the binary, so a `build.policy: human` build
stays installed. When `reset_app_data: never`, nobody calls it.

It exits non-zero whenever it could not wipe — the app is not installed, no
device is booted, `simctl` reported a container path it does not recognise, `pm
clear` did not report success. That is deliberate: a reset that quietly did
nothing hands the next test yesterday's state, and the cost lands much later, as
a flaky test nobody traces back to here. If a caller genuinely does not mind,
`|| true` says so explicitly.

## 7. Verify

`scripts/setup-all.sh --check` should end all green, and
`pytest --collect-only` inside the test dir should succeed (0 tests is fine).
- `scripts/scaffold-memory.sh --check` should print `memory scaffold: OK`
  followed by `memory lint: OK` — it runs `agentqa-write-test`'s `memory-lint.py`
  over the store, because a structurally complete store can still be full of
  notes Recall can't use.
- `scripts/scaffold-permissions.sh --check` should print `permission scaffold: OK`
