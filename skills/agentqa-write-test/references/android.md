# Android — the platform delta

Read this when `platform: android` in `.agentqa/config.yml`. **Everything in
SKILL.md still applies** — the 0–9 flow, the clarify questions, the checkpoints,
the memory model, "only the live hierarchy is truth", no sub-agents. This file
only replaces the iOS-specific *mechanics* at each step. Where SKILL.md shows an
`xcrun`/`simctl` command, a `bundle_id`, or `accessibilityIdentifier`, use the
Android equivalent here.

The app id on Android is the **`app_package`** (with `app_activity` as the
launcher). `reset-app-data.sh`, `conftest.py`, and `agent-device` all resolve it
from the config — you rarely type it.

Sections: Device & driver · Reset · Reading the hierarchy · Identifiers (the
crux) · Verify · Locators · System dialogs · Build · Preconditions & phantoms.

## Device & driver

UiAutomator2 driver over `adb`, against a booted emulator (AVD) or a connected
device. The scaffold `conftest.py` builds it from the config; you don't wire it
by hand. For the step-3 exploration, agent-device drives Android the same way it
drives iOS — just name the platform:

```bash
agent-device open <app_package> --platform android
agent-device snapshot -i
agent-device press <ref> --settle        # same inspect → act → settle loop
```

If several devices are attached, `ANDROID_SERIAL=<serial>` picks one (both
agent-device and the reset script honor it).

## Reset (Phase 2 / conftest)

`reset_app_data: always` → `adb shell pm clear <app_package>`: clears the app's
data + cache **and revokes its runtime permissions**, keeping the APK installed
(a `build.policy: human` build survives). This is the Android parallel of the iOS
container wipe + privacy reset. `agentqa-init`'s `scripts/reset-app-data.sh` does
it for the non-pytest explore launches; `conftest.py` does it for the suite.

Consequence — the same one as iOS: because permissions are revoked, **runtime
permission dialogs re-fire on every wiped launch**, so the test must dismiss them
in setup (see System dialogs).

## Reading the hierarchy

`agent-device snapshot` is still your source of truth. When you pull Appium
`page_source`, expect Android XML: nodes are `android.widget.*` /
`androidx.compose.ui.*` with attributes `resource-id`, `content-desc`, `text`,
`class`, `clickable`, `package`, `bounds`. Two things to watch:

- **native vs web:** an `android.webkit.WebView` node is a web surface whose DOM
  is *not* in the native tree — treat it exactly like an iOS `WKWebView`
  (`[web]` in memory: read it by screenshot, address it by visible text; a native
  automation locator won't see inside it). A true webview context switch needs a
  matching chromedriver, which is out of scope for most flows.
- **`package=`** tells you whether a node belongs to your app or to the system —
  the key to spotting the permission dialog below.

## Identifiers (Phase 3A) — additive, the crux

The rule is identical to iOS: **add** an identifier, change nothing about
behavior, layout, or logic, and `git diff --numstat` must show **0 deletions**.
Names follow the same `identifier_convention` (e.g. `login_username_field`) and
are logged in the screen note the same way. Only the mechanism differs — pick by
UI toolkit:

### contentDescription — the recommended default

Maps to Appium's **accessibility id** locator, the *same* strategy iOS uses for
`accessibilityIdentifier` — so the page objects look identical across platforms.

- **XML views:** `android:contentDescription="login_username_field"` (additive
  attribute), or in code `usernameField.contentDescription = "login_username_field"`.
- **Compose:** `Modifier.semantics { contentDescription = "login_username_field" }`
  (additive modifier).
- Surfaces in `page_source` as `content-desc="login_username_field"`.
- **Tradeoff to weigh:** contentDescription is spoken by TalkBack. On a control
  that already needs a meaningful spoken label this is free; on a purely-visual
  test hook it changes the accessibility experience — prefer a testTag there.

### resource-id — `android:id` / Compose `testTag`

- **XML views:** `android:id="@+id/login_username_field"` → `page_source`
  `resource-id="<app_package>:id/login_username_field"`. Adding one is additive;
  many already exist.
- **Compose:** `Modifier.testTag("login_username_field")` **plus**, once at the
  tree root, `Modifier.semantics { testTagsAsResourceId = true }` — without that
  flag a testTag is invisible to Appium. Both are additive.

**Which to use:** default to **contentDescription** for parity with iOS (same
accessibility-id locator, one page-object shape). Reach for **testTag →
resource-id** when you must not alter the spoken a11y label, or when the screen is
Compose and already uses testTags.

## Verify in the live hierarchy (Phase 3B)

Pull `page_source` and grep for the new names:

- contentDescription → `content-desc="login_username_field"`
- resource-id → `resource-id="<app_package>:id/login_username_field"`

Missing? Fix the placement (contentDescription/testTag on the right node; for
testTag confirm `testTagsAsResourceId = true` is set at the root), then rebuild —
back to Phase 3A and its build checkpoint. Refresh the observation to
`verified-in-hierarchy` on success.

## Locators (Phase 4)

```python
from appium.webdriver.common.appiumby import AppiumBy

# content-desc — identical to the iOS accessibility-id page object
USERNAME = (AppiumBy.ACCESSIBILITY_ID, "login_username_field")
# resource-id
SUBMIT   = (AppiumBy.ID, "com.example.app:id/login_submit_button")
# UiAutomator fallback (rich selectors)
ERROR    = (AppiumBy.ANDROID_UIAUTOMATOR,
            'new UiSelector().resourceId("com.example.app:id/login_error_label")')
# UI you don't own — WebView / system dialog — match by visible text
ALLOW    = (AppiumBy.XPATH, '//*[@text="Allow"]')
```

Your identifiers for app-owned UI; visible-text only for what you don't own.
Credentials still come only from the env-var names in the config.

## System dialogs (Phase 2 + test setup)

The **runtime permission dialog** is owned by the permission-controller package
(`com.google.android.permissioncontroller`, or `com.android.permissioncontroller`
on older OS), **not your app** — its nodes carry that `package=` and no app-code
change can label them, exactly like an iOS SpringBoard alert. Handle it the same
way SKILL.md demands for iOS:

- **Don't guess the tap — ask the user** (allow / deny / dismiss) the first time
  you hit it in exploration. That's the expected step-3 escalation, not a second
  clarify round.
- Match the button by visible text: `Allow`, `While using the app`,
  `Allow only while using the app`, `Don't allow`, `Deny`. The buttons also carry
  stable ids like `com.android.permissioncontroller:id/permission_allow_button`.
- Because `pm clear` revokes permissions, the dialog fires on **every** wiped
  launch — record it as a `[quirk]` with the chosen action and dismiss it in the
  test's setup, before the flow under test starts. A test that assumes a clean
  first screen fails on a fresh device.
- If the user's choice is "allow" and you want it deterministic, `adb shell pm
  grant <app_package> <permission>` in setup is an option — but only after the
  user picks allow; still don't guess.

Other outside-the-app surfaces to watch on each snapshot: ANR ("… isn't
responding"), the "app keeps stopping" crash dialog, and system-update / battery
prompts. Treat them like iOS pop-ups — stop and ask.

## Build (Phase 3 checkpoint)

- `human` → ask the user to build & install (Android Studio, or
  `./gradlew :app:installDebug`); never run the build yourself.
- `agent` → `./gradlew installDebug` is usually viable because a debug build
  needs no signing — but still respect the config; if it says `human`, hand off.

## Preconditions & phantoms

Preconditions (green loop):

```bash
adb devices | awk '$2=="device"' | grep -q .          # device/emulator up
adb shell pm list packages | grep -q <app_package>    # app installed
nc -z 127.0.0.1 4723                                  # appium server up
```

Android phantom signatures worth a `failures/` note when you hit them:

- **UiAutomator2 server** fails to install / instrumentation crashes on the first
  session → retry once; if it recurs, `adb uninstall io.appium.uiautomator2.server`
  (+ `.test`) and let Appium reinstall.
- **`adb` device offline / unauthorized** → re-accept the RSA prompt on the
  device, or `adb kill-server && adb start-server`.
- **Busy host** slows the u2 server the same way it slows WebDriverAgent — the
  "never index/CPU-load while tests run" rule applies verbatim.
