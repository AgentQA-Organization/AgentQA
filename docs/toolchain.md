# The toolchain

`/agentqa-init setup` installs and validates the tools below. Each is
**optional-with-a-fallback**, so the skills still work (with less automation) when
one is missing. Installing them is a one-time-per-machine step; see
[`installation.md`](installation.md).

## Requirements

- **Node.js** and **Python 3.9+**.
- **iOS:** macOS with Xcode + an iOS simulator.
- **Android:** the Android SDK (`adb`, an emulator or device) + a JDK (macOS or
  Linux).

Pinned tool versions live in
[`skills/agentqa-init/scripts/common.sh`](../skills/agentqa-init/scripts/common.sh).

## The tools

| Tool | What it is | Why the skills use it |
|---|---|---|
| **Appium 2.x + the platform driver** | The mobile automation server + the driver for your platform: **XCUITest** for iOS (WebDriverAgent under the hood) or **UiAutomator2** for Android (`adb`). `setup` installs whichever the platform scope needs. | The engine your generated pytest tests drive the app through, and the source of `page_source` — the one source of truth. |
| **agent-device** | A cross-platform CLI that is the agent's "hands" on the device (`open`, `snapshot -i`, `press`/`fill --settle`, `screenshot`) — drives iOS simulators and Android emulators/devices alike. | Lets the agent **explore the real app** before writing a test — walking the flow, reading the live view hierarchy, seeing what actually renders (native vs. web). |
| **CodeGraph** | A codebase index + query MCP (call chains, blast radius). | Helps the agent map a flow to the screens/symbols in your source and see what a change touches — *before* it edits, so identifier additions stay surgical. |
| **Appium MCP** (`appium-mcp`) | An MCP server that talks to a running Appium session. | First-class `page_source` and identifier-verification reads while writing/diagnosing a test, instead of shelling out. |
| **Python venv + pytest** | The test harness. `conftest.py` auto-attaches to the booted device (simulator or emulator), saves `page_source` + a screenshot on any failure, and writes a per-run execution runbook + final screenshot to `artifacts/runbook/` on pass or fail. | Runs the tests and captures failure evidence for diagnosis. |

## MCP servers

The MCP servers (`codegraph`, `appium`) are defined once in a portable
`.agentqa/mcp.json`. On Claude Code they auto-register; on other harnesses `setup`
prints where to import them.

Behavioral memory needs **no server of its own** — it's plain Markdown plus three
small stdlib scripts. See [`memory.md`](memory.md).

## Do not run CPU-heavy jobs during device tests

**Never run a CPU-heavy job (e.g. re-indexing CodeGraph) while device tests are
running.** On iOS, WebDriverAgent waits time out; on Android, a busy host slows the
UiAutomator2 server. Both surface as **phantom failures** that look like real
test failures but aren't.

## See also

- [`installation.md`](installation.md) — how to install these
- [`architecture.md`](architecture.md) — why `page_source` is the one source of truth
- [`workflow.md`](workflow.md) — where each tool is used in a run
- [`memory.md`](memory.md) — the memory store that needs no server
