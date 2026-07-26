# AgentQA Studio — UI redesign (design)

**Date:** 2026-07-26
**Status:** Approved (direction + interactive mockup signed off)
**Scope:** Restyle the Studio dashboard's three static files. No server, endpoint,
protocol, or JS-behavior-contract changes.

---

## Goal

Give the Studio dashboard (`http://127.0.0.1:7332/`) a clearer visual hierarchy, a
more polished Agent conversation + stepper, and a deliberate dark theme — by porting
the visual language of a Figma Make redesign onto the **existing, untouched** wiring.

The redesign was validated as an interactive, self-contained mockup before this spec
was written. This document is the source of truth for the port into the real files.

## Source materials

- **Figma Make** "Modern-Website-Design" (`App.tsx`) — a React + Tailwind + Google-Fonts
  mockup. Used for *visual language only*; its stack is incompatible with our constraints.
- **UI feature summary** (`src/imports/studio-ui-feature-summary.md` in the Figma; the
  behavior contract lives there) — the authority on *what must keep working*.
- **Current UI:** `studio/static/index.html`, `app.js`, `style.css`.
- **Approved mockup:** self-contained vanilla HTML/CSS/JS with seed data across all key
  states (built during brainstorming; becomes the basis for the port).

---

## Hard constraints (non-negotiable)

- **Vanilla HTML/CSS/JS.** No framework, no npm, no build step, no external assets (no
  CDN, no remote fonts/images). Everything ships in `studio/static/`, inline or bundled.
- **Single page**, **theme-aware** (light + dark), **responsive** (wide content scrolls
  inside its own container; the page body never scrolls sideways).
- **Accessible:** real `<label>`s, keyboard-usable controls, visible focus, sufficient
  contrast in both themes.

## Decisions (locked with the user)

1. **Layout model — tabbed nav.** One panel visible at a time (Rig / Tests / Memory /
   Agent). The tab bar carries per-tab **status dots** so at-a-glance signal survives
   without every panel being open: Rig = red when any rig check fails; Tests = blue
   pulse while a run streams; Agent = amber (pulse) when a card is waiting, blue pulse
   while working. Opens on **Agent** (the interactive heart).
2. **Feel — roomy (match Figma).** Centered ~1024px column, generous padding, 12px
   cards, emerald accent.

## Forced deviations from the Figma (all deliberate)

| Figma uses | Why it can't ship | Substitution |
|---|---|---|
| Tailwind utility classes | no build step | Hand-written CSS with custom-property tokens mirroring the slate/emerald values |
| Inter + JetBrains Mono via Google Fonts `@import` | no external assets | System stacks: `system-ui` (UI), `ui-monospace, SFMono-Regular, Menlo` (code/data) |
| Seed data + local React state | it's a mockup | Real `fetch`/SSE wiring, unchanged |

---

## Visual system

**Neutrals** are *slate* (a blue-biased grey — chosen, not a default mid-grey).
**Accent** is **emerald** (`#059669` light / `#34d399` dark) — brand mark, active tab,
"ok" status, done stepper phases. Semantic colors are kept separate from the accent:

- **Primary action / active step:** blue `#2563eb`.
- **Waiting / warn:** amber `#f59e0b` (light) / `#fbbf24` (dark).
- **Fail / reject / danger:** red `#dc2626` (light) / `#f87171` (dark).
- **Terminal + diff:** a constant dark code surface (`#0b1020`) in *both* themes — a
  deliberate classic-terminal choice, matching today's `.output`/`.diffbox`.

**Tokens.** The palette is CSS custom properties on `:root` (light default), redefined
under `@media (prefers-color-scheme: dark)` **and** re-defined again under
`:root[data-theme="dark"]` / `:root[data-theme="light"]` so the manual toggle wins over
the OS preference in both directions. Components style **through tokens only** — never a
raw color inside the media query.

**Type.** `system-ui` for UI; `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
monospace` for all data, config, code, test-file names, and the stepper. A native-devtool
feel, and exactly what the real files must use.

**Layout.** Sticky translucent header (emerald flask mark · mono config summary · theme
toggle) → tab bar (underline-active + status dots) → centered `max-width: 1024px` column,
`gap`-based flex/grid stacks, `border-radius: 12px` cards with a subtle shadow.

**Theme toggle.** New, client-only. Stamps `data-theme` on `<html>`, persists to
`localStorage` (wrapped in try/catch), and updates the sun/moon icon. Default remains
`prefers-color-scheme` until the user overrides.

---

## Panels (all from existing endpoints — no new data)

### Header / config
Brand mark + name, config summary as `<platform pill> app_id · build:<policy> · appium:<port>`
in mono, theme toggle. States: loading / loaded / error (unchanged data from `/api/config`).

### 1. Rig
2×2 grid of icon cards (✓ emerald / ⚠ muted) from `/api/rig`, each showing OK / Not ready.
A **derived** summary line — "N ready · M not ready" + the CodeGraph warning when any check
fails. *Refresh* button preserved. States: checking / loaded / error.

### 2. Tests
Two columns: a **file-list sidebar** (`Run all` in the header; per-file `Run`) and a
**terminal** output card. Live SSE stream fills the terminal; `FAILED`/`Timeout` lines
render red, `[exit N]` green/red, the `$` command line dimmed; an `exit N` badge appears in
the card header on completion. A collapsible **Last failures** section lists artifact names.
States: idle / running (buttons disabled) / done / error.

> **Flagged server change (not in this spec):** the Figma shows `.xml`/`.png` buttons on
> failure rows. The server currently exposes artifact *names* only. Rendered as **inert
> labels** with a one-line note; making them downloadable is a separate server/route change.

### 3. Memory
Two columns: a **groups sidebar** (flows / screens / failures, `⚠` on notes whose content
is stale) and a **note viewer**. The viewer does a **safe, light** markdown render (headings;
`Identifiers:` / `Key assertion:` / `Verified:` key-value lines) — **every fragment through
`esc()`**, DOM built without interpolating unescaped note text. `env.md` present/absent chip;
`Check stale` / `Lint` produce a result banner (warn / ok / bad). States: loaded / note open /
result / unavailable / error.

### 4. Agent (interactive heart)
- **Attach indicator** — disconnected (muted) / idle (emerald) / working (emerald pulse) /
  waiting (amber pulse) / stale-heartbeat (red). Status-aware exactly as today.
- **Stepper card** — `map · clarify · explore · identifiers · build · verify · write · green ·
  review · capture`, each done / active / upcoming, **derived only from the `stage` slug**;
  unknown slugs still render. Hidden when there is no current phase.
- **Job-input card** — labeled "Write a test for", text input + `Start`; Enter submits;
  disabled while a job runs; queues when no agent is attached.
- **Conversation card** — append-only, scrollable, **bounded to ~500 entries**. Renders
  progress lines (with a `stage` chip), terminal results (green success + test path, or
  abandoned), error lines, and the four **card types**:

  | Card (protocol `kind`/`subtype`) | Controls | Reply payload |
  |---|---|---|
  | **Clarify** (`form`) | text inputs + choice radios/segments, some pre-filled | `{reply_to, answers}` |
  | **Permission** (`form`, single choice) | Allow / Deny / Dismiss | `{reply_to, answers}` |
  | **Build** (`confirm`) | "I've built & installed" | `{reply_to, decision:"built"}` |
  | **Review** (`review`) | additions-only diff + each test file in own scroll box; Approve / Reject (reject reveals a note) | `{reply_to, decision:"approve"}` / `{decision:"reject", note?}` |

  Each card is **active** → optionally **submitting** (controls disabled) → **locked** (a
  `↳ answered/built/approved/rejected` marker), with an **error** state that re-enables
  controls to retry. Cards gain a header kind-label (from `kind`/`subtype`, no new data).

---

## Behavior contract — preserved verbatim

Restyle structure and the small render helpers only. Keep:

- The **API endpoints** called and the **reply payload shapes** POSTed.
- **SSE streaming** for both the runner and the agent outbox, including reconnect where the
  transcript replays and the client **dedupes by record id** (`seenRecordIds`).
- **`esc()` XSS-escaping** of every agent/user string rendered into the DOM; any new
  interpolation goes through it too.
- The **stepper derives only from the `stage` slug**, never step numbers, and renders
  unknown slugs.
- The **bounded log** (~500 entries) and the **status-aware attach indicator** (running +
  stale heartbeat = "working", not "disconnected").

Functions kept by name: `fetchJSON`, `esc`, `el`, `connectStream`, `dispatch`, `sendReply`,
and the run-stream `EventSource` handling. New code is additive: a tab controller and the
theme toggle.

---

## Implementation shape

Port the approved mockup into the three real files:

- **`index.html`** — new structure: header (brand, config, theme toggle), tab bar, four
  `role="tabpanel"` sections. Keep element IDs the JS wiring reads (`config`, `rig`, `tests`,
  `run-output`, `memory`, `note-view`, `agent-log`, `stepper`, `job-idea`, `job-start`,
  `agent-status`, …) — or update `app.js` selectors in lockstep where renamed.
- **`style.css`** — the token system + component styles from the mockup. **Keep a `.stepper`
  class** (asset smoke test asserts it).
- **`app.js`** — keep all wiring; restyle the DOM built by `loadRig`, `loadTests`,
  `loadMemory`, `renderStepper`, `renderCard`/`renderForm`/`renderConfirm`/`renderReview`,
  the progress/result/error appenders; add `showTab()` + tab-dot painting and the theme
  toggle. **Keep `connectStream`** (asset smoke test asserts it).

## Testing

- **Asset smoke test stays green** without edits: `app.js` keeps `connectStream`, `style.css`
  keeps `.stepper`. Run: `.devvenv/bin/pytest studio/tests/test_server.py -v`.
- **Manual smoke:** launch the daemon against a repo with `.agentqa/`
  (`.devvenv/bin/python -m studio.server --repo <that repo> --port 7332 --open`); confirm all
  four panels render, tabs + dots + theme toggle work, tests stream, and the Agent cards still
  submit (`{answers}` / `{decision:"built"}` / approve / reject).

## Out of scope

- Any server, endpoint, protocol, or reply-shape change.
- Downloadable failure artifacts (`.xml`/`.png`) — flagged above as a separate change.
- New config fields in the header beyond today's summary line.

## Risks

- **Selector drift** between `index.html` IDs and `app.js`: the highest-risk part of the port.
  Mitigate by keeping IDs stable, or changing HTML + JS together and smoke-testing.
- **Safe markdown render** in the note viewer must not introduce an XSS path — build DOM with
  escaped text only, never `innerHTML` with raw note content.
