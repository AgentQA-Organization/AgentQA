# AgentQA Studio UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the AgentQA Studio dashboard's three static files into the approved tabbed, slate + emerald design — over the existing, untouched server/protocol/JS wiring.

**Architecture:** Port a validated, self-contained mockup into `studio/static/index.html` + `app.js` + `style.css`. `style.css` is replaced wholesale with a CSS-custom-property token system. `index.html` becomes a header + tab bar + four `role="tabpanel"` sections, **keeping every element ID the current `app.js` reads** so the fetch/SSE wiring keeps resolving. `app.js` keeps all wiring verbatim; only the small DOM-building helpers are restyled, plus two additive features (tab controller, theme toggle).

**Tech Stack:** Vanilla HTML/CSS/JS (no framework, no build). Python daemon serves the static files. Tests: pytest (`.devvenv/bin/pytest`).

**Source of truth:**
- Spec: `docs/superpowers/specs/2026-07-26-agentqa-studio-ui-redesign-design.md`
- Approved mockup (validated, interactive, seed data): `/private/tmp/claude-501/-Users-anhtuannguyen-Documents-GitHub-AgentQA-iOS/d5146745-e409-4da1-9fe4-82c5a35b017d/scratchpad/studio-mockup.html` (also published: https://claude.ai/code/artifact/10e20a87-9f9d-4e6a-94f6-a10bff5d5ff4). The mockup's `<style>` block **is** the target stylesheet; its `<script>` render functions are the target DOM shapes (adapted here to real IDs + real data).

## Global Constraints

Every task's requirements implicitly include these:

- **Vanilla HTML/CSS/JS only.** No framework, no npm, no build step, **no external assets** (no CDN, no remote fonts/images). Everything inline or in `studio/static/`.
- **Fonts:** system stacks only — `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (UI) and `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace` (mono).
- **Single page**, **theme-aware** (light + dark), **responsive** (wide content — terminal output, review diff — scrolls inside its own container; page body never scrolls sideways).
- **Accessible:** real `<label>`s, keyboard-usable controls, visible `:focus-visible`, `prefers-reduced-motion` respected.
- **Preserve the behavior contract — do NOT change:** the API endpoints called; reply payload shapes (`{reply_to, answers}`, `{reply_to, decision:"built"}`, `{reply_to, decision:"approve"}`, `{reply_to, decision:"reject", note?}`); SSE streaming + reconnect **dedupe by record id** (`seenRecordIds`); `esc()` on every agent/user string put in the DOM; the stepper derived **only** from the `stage` slug (renders unknown slugs); the ~500-entry bounded log; the status-aware attach indicator.
- **Smoke-test invariants (must stay literally present):** `index.html` body contains the text `AgentQA Studio`; `app.js` contains `connectStream`; `style.css` contains `.stepper`. (`studio/tests/test_server.py` asserts these.)
- **Keep these `app.js` function names:** `fetchJSON`, `esc`, `el`, `connectStream`, `dispatch`, `sendReply`, `renderStepper`, `pollAgentState`, `startJob`, and the run-stream `EventSource` handling.
- **Do not touch** any file under `studio/` other than the three static files (no server/protocol/module changes). Downloadable failure artifacts (`.xml`/`.png`) are **out of scope** — render inert labels.

**Element IDs to keep (index.html ↔ app.js contract):** `config`, `rig`, `tests`, `run-output`, `memory`, `note-view`, `agent-status`, `stepper`, `agent-log`, `job-idea`, `job-start`, `stale-btn`, `lint-btn`, and the `data-refresh="rig"` / `data-refresh="memory"` buttons. **New IDs added:** `theme-toggle`, `rig-summary`, `exit-badge`, `failures-toggle`, `failures-body`, `mem-banner`. (`mem-health` is removed; lint/stale output moves to `mem-banner`.)

**Per-task loop (verification for a UI port):** because the dashboard has no unit tests for rendered output, each task's verification is: (a) `.devvenv/bin/pytest studio/tests/test_server.py -v` stays green, and (b) a manual check in the browser. Manual smoke needs a repo that has `.agentqa/` (this repo does not); point the daemon at a configured app repo:
`.devvenv/bin/python -m studio.server --repo <app-repo-with-.agentqa> --port 7332 --open`

---

## File Structure

- **`studio/static/style.css`** — replaced wholesale (Task 1). Token system + all component styles. One file, one responsibility (presentation).
- **`studio/static/index.html`** — restructured (Task 1): header (brand + config + theme toggle), tab bar, four panel sections. Panel inner containers keep stable IDs; per-panel markup detail filled by the JS render helpers.
- **`studio/static/app.js`** — wiring preserved; DOM-render helpers restyled per panel (Tasks 2–5) + tab controller / theme toggle / tab-dot painter added (Task 1).

---

## Task 1: Frame — stylesheet, shell HTML, tabs + theme toggle

Establishes the new chrome. After this task the app loads in the new shell, tabs switch, and the theme toggle works; panels still render with their **current** helpers (restyled in Tasks 2–5), so panel interiors look unstyled until then — that is expected.

**Files:**
- Modify (replace): `studio/static/style.css`
- Modify (replace): `studio/static/index.html`
- Modify: `studio/static/app.js` (add shell JS near the top, after `el()`; leave all existing wiring)
- Test: `studio/tests/test_server.py`

**Interfaces produced (used by later tasks):**
- CSS classes: `.card`, `.card.pad`, `.card-head`, `.card-title`, `.btn` (+ `.sm`/`.xs`/`.btn-primary`/`.btn-success`/`.btn-danger`), `.panel`/`.panel.active`, `.panel-head`, `.rig-grid`/`.rig-cell`/`.rig-ico`/`.rig-summary`/`.legend`/`.rig-warn`, `.split`/`.filelist`/`.file-row`/`.terminal`/`.term-body`/`.exit-badge`/`.failures-toggle`/`.failures-body`/`.fail-row`, `.mem-groups`/`.mem-ghead`/`.mem-note`/`.note-view`/`.nv-body`/`.nv-tag`/`.chip`/`.result-banner`, `.attach`/`.stepper`/`.step`/`.step-sep`/`.job-form`/`.input`/`.convo`/`.prog`/`.result`/`.msg-card`/`.mc-*`/`.field`/`.segmented`/`.seg`/`.diffbox`/`.card-actions`. (All defined in the mockup's `<style>`.)
- JS globals: `SVG_CHECK`, `SVG_WARN` (icon strings), `paintTabDots()` (repaints tab status dots from current state), `showTab(name)`.

- [ ] **Step 1: Replace `style.css` with the mockup stylesheet**

Copy the **entire contents of the `<style>` block** from the approved mockup file (path in "Source of truth" above) into `studio/static/style.css` (drop the surrounding `<style>`/`</style>` tags). Keep the leading comment. Confirm the file contains `.stepper` (smoke-test invariant) and the `:root` / `@media (prefers-color-scheme: dark)` / `:root[data-theme="dark"]` / `:root[data-theme="light"]` token blocks.

- [ ] **Step 2: Replace `index.html` structure**

Replace `studio/static/index.html` with the structure below. Note: it keeps the text `AgentQA Studio`, keeps all stable IDs, uses `data-refresh` buttons for rig/memory refresh, and links `style.css` + `app.js` exactly as today.

```html
<!doctype html>
<meta charset="utf-8">
<title>AgentQA Studio</title>
<link rel="stylesheet" href="/static/style.css">

<header class="app">
  <div class="wrap">
    <div class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v5.5L4.9 17A2 2 0 0 0 6.6 20h10.8a2 2 0 0 0 1.7-3L14 8.5V3"/></svg>
        </span>
        <span class="brand-name">AgentQA Studio</span>
      </div>
      <div class="config mono" id="config" aria-label="Configuration">loading config…</div>
      <button class="icon-btn" id="theme-toggle" aria-label="Toggle theme" title="Toggle light / dark">
        <svg id="icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20.35 15.35A9 9 0 0 1 8.65 3.65 9 9 0 1 0 20.35 15.35Z"/></svg>
        <svg id="icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" style="display:none"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      </button>
    </div>
    <nav class="tabs" role="tablist" aria-label="Panels">
      <button class="tab" role="tab" data-tab="rig" aria-selected="false">Rig</button>
      <button class="tab" role="tab" data-tab="tests" aria-selected="false">Tests</button>
      <button class="tab" role="tab" data-tab="memory" aria-selected="false">Memory</button>
      <button class="tab" role="tab" data-tab="agent" aria-selected="true">Agent</button>
    </nav>
  </div>
</header>

<main>
  <section class="panel" id="panel-rig" role="tabpanel" aria-label="Rig">
    <div class="panel-head">
      <div><h2>Rig status</h2><div class="subtitle">Machine readiness for running tests</div></div>
      <button class="btn" data-refresh="rig">Refresh</button>
    </div>
    <div class="rig-grid" id="rig"></div>
    <div class="card pad"><div class="card-title" style="margin-bottom:10px">Summary</div><div class="rig-summary" id="rig-summary"></div></div>
  </section>

  <section class="panel" id="panel-tests" role="tabpanel" aria-label="Tests">
    <div class="panel-head">
      <div><h2>Test runner</h2><div class="subtitle">pytest suite</div></div>
      <button class="btn btn-primary" id="run-all">Run all</button>
    </div>
    <div class="split">
      <div class="card filelist"><div class="card-head"><span class="card-title">Test files</span></div><div id="tests"></div></div>
      <div class="card terminal"><div class="card-head"><span class="card-title">Output</span><span class="exit-badge" id="exit-badge"></span></div><div class="term-body" id="run-output"><span class="placeholder">Run a test to see output here.</span></div></div>
    </div>
    <div class="card" id="failures-card" hidden>
      <button class="failures-toggle" id="failures-toggle" aria-expanded="false"><span class="row-gap"><span class="tdot warn"></span> <span id="failures-label">Last failures</span></span><svg class="chev" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></button>
      <div class="failures-body" id="failures-body" hidden></div>
    </div>
  </section>

  <section class="panel" id="panel-memory" role="tabpanel" aria-label="Memory">
    <div class="panel-head">
      <div><h2>Memory</h2><div class="subtitle">Flows · screens · failures</div></div>
      <div class="row-gap">
        <span class="chip ok" id="env-chip" hidden>env.md present</span>
        <button class="btn sm" data-refresh="memory">Refresh</button>
        <button class="btn sm" id="stale-btn">Check stale</button>
        <button class="btn sm" id="lint-btn">Lint</button>
      </div>
    </div>
    <div id="mem-banner"></div>
    <div class="split">
      <div class="card mem-groups" id="memory"></div>
      <div class="card note-view" id="note-view"><div class="nv-empty">Select a note to view</div></div>
    </div>
  </section>

  <section class="panel" id="panel-agent" role="tabpanel" aria-label="Agent">
    <div class="panel-head">
      <div><h2>Agent</h2><div class="subtitle">Test authoring via Claude Code</div></div>
      <span class="attach" id="agent-status"><span class="adot"></span><span id="attach-label">checking for agent…</span></span>
    </div>
    <div class="card pad" id="stepper-card" style="display:none"><div class="card-title" style="margin-bottom:11px">Progress</div><div class="stepper" id="stepper"></div></div>
    <div class="card pad">
      <label for="job-idea" class="card-title" style="display:block;margin-bottom:8px">Write a test for</label>
      <div class="job-form"><input class="input" id="job-idea" type="text" autocomplete="off" placeholder="e.g. the guest checkout happy path"><button class="btn btn-primary" id="job-start">Start</button></div>
    </div>
    <div class="card"><div class="card-head"><span class="card-title">Conversation</span><span class="mono muted" id="convo-count" style="font-size:12px"></span></div><div class="convo agent-log" id="agent-log"></div></div>
  </section>
</main>

<script src="/static/app.js"></script>
```

Note: `#agent-log` also carries the legacy `agent-log` class harmlessly; the `.convo` class is what's styled. `#stepper-card` starts hidden and is shown by `renderStepper` (Task 5).

- [ ] **Step 3: Add shell JS to `app.js`**

Insert the following **after** the `el()` helper (near the top). These are additive; do not remove anything.

```js
const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>';
const SVG_WARN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>';

// ---- Theme toggle (client-only) ----------------------------------------
(function theme() {
  const root = document.documentElement;
  let stored = null;
  try { stored = localStorage.getItem("aqa-theme"); } catch (e) {}
  if (stored) root.setAttribute("data-theme", stored);
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => {
    const a = root.getAttribute("data-theme");
    return a ? a === "dark" : mq.matches;
  };
  const paint = () => {
    document.getElementById("icon-sun").style.display = isDark() ? "block" : "none";
    document.getElementById("icon-moon").style.display = isDark() ? "none" : "block";
  };
  document.getElementById("theme-toggle").onclick = () => {
    const next = isDark() ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("aqa-theme", next); } catch (e) {}
    paint();
  };
  mq.addEventListener("change", paint);
  paint();
})();

// ---- Tabs ---------------------------------------------------------------
const TAB_NAMES = ["rig", "tests", "memory", "agent"];
function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.tab === name)));
  TAB_NAMES.forEach((n) => document.getElementById("panel-" + n).classList.toggle("active", n === name));
}
document.querySelectorAll(".tab").forEach((t) => { t.onclick = () => showTab(t.dataset.tab); });

// Repaint per-tab status dots from current state. Called by loaders/pollers.
const tabState = { rig: null, tests: null, agent: null };
function setTabDot(tab, cls /* "warn"|"alert"|"busy"|null */) {
  tabState[tab] = cls;
  const btn = document.querySelector(`.tab[data-tab="${tab}"]`);
  if (!btn) return;
  const old = btn.querySelector(".tdot");
  if (old) old.remove();
  if (cls) btn.appendChild(el(`<span class="tdot ${cls}${cls !== "warn" ? " pulse" : ""}"></span>`));
}
function paintTabDots() { /* no-op hook; panels call setTabDot directly */ }

showTab("agent");
```

- [ ] **Step 4: Verify smoke test green + app boots**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v`
Expected: PASS (asserts `AgentQA Studio` in HTML, `connectStream` in app.js, `.stepper` in style.css — all still present).

Then load the daemon against an app repo with `.agentqa/` and confirm: page renders in the new shell, all four tabs switch, the theme toggle flips light/dark and persists across reload.

- [ ] **Step 5: Commit**

```bash
git add studio/static/style.css studio/static/index.html studio/static/app.js
git commit -m "feat(studio): new tabbed shell — tokens, header, tabs, theme toggle"
```

---

## Task 2: Rig panel render

**Files:**
- Modify: `studio/static/app.js` (replace `loadRig`; add `renderRigSummary`)
- Test: `studio/tests/test_server.py`

**Interfaces:**
- Consumes: `SVG_CHECK`, `SVG_WARN`, `setTabDot` (Task 1); `fetchJSON`, `esc`, `el` (existing); `/api/rig` → `{simulator, app_installed, appium, codegraph}` (booleans).
- Produces: none downstream.

- [ ] **Step 1: Replace `loadRig` and add the summary helper**

```js
async function loadRig() {
  const box = document.getElementById("rig");
  try {
    const r = await fetchJSON("/api/rig");
    const items = [
      ["simulator", "Simulator booted"],
      ["app_installed", "App installed"],
      ["appium", "Appium running"],
      ["codegraph", "CodeGraph indexed"],
    ];
    box.innerHTML = "";
    let ready = 0;
    for (const [key, label] of items) {
      const ok = !!r[key];
      if (ok) ready++;
      box.appendChild(el(
        `<div class="card rig-cell"><div class="rig-ico ${ok ? "ok" : "bad"}">${ok ? SVG_CHECK : SVG_WARN}</div>` +
        `<div><div class="label">${esc(label)}</div><div class="state ${ok ? "ok" : "bad"}">${ok ? "OK" : "Not ready"}</div></div></div>`));
    }
    renderRigSummary(items.length, ready);
    setTabDot("rig", ready < items.length ? "warn" : null);
  } catch (err) {
    box.textContent = `rig error: ${err.message}`;
  }
}

function renderRigSummary(total, ready) {
  const sum = document.getElementById("rig-summary");
  const not = total - ready;
  sum.innerHTML = "";
  sum.appendChild(el(`<span class="legend"><span class="dot" style="background:var(--accent)"></span>${ready} ready</span>`));
  sum.appendChild(el(`<span class="legend"><span class="dot" style="background:var(--danger)"></span>${not} not ready</span>`));
  if (not > 0) sum.appendChild(el(`<span class="rig-warn">⚠ some checks not ready — identifiers may be incomplete</span>`));
}
```

- [ ] **Step 2: Verify**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v` → PASS.
Manual: Rig tab shows the 2×2 icon cards + "N ready · M not ready" summary; a failing check (e.g. CodeGraph not indexed) shows the red dot on the Rig tab and the warning line; Refresh re-checks.

- [ ] **Step 3: Commit**

```bash
git add studio/static/app.js
git commit -m "feat(studio): restyle Rig panel as icon cards + summary"
```

---

## Task 3: Tests panel render

**Files:**
- Modify: `studio/static/app.js` (replace `loadTests`, `runTests`; add `termLine`, `renderFailures`)
- Test: `studio/tests/test_server.py`

**Interfaces:**
- Consumes: `setTabDot`, `el`, `esc`, `fetchJSON` (existing); `/api/tests` → `{tests: string[], artifacts: [{name, xml, png?}]}`; `/api/run` (POST → `{run_id}`) and `/api/run/stream?id=` (SSE) — **wiring unchanged**.
- Produces: none downstream.

- [ ] **Step 1: Replace `loadTests` (file rows + failures section)**

```js
async function loadTests() {
  const box = document.getElementById("tests");
  try {
    const data = await fetchJSON("/api/tests");
    box.innerHTML = "";
    for (const t of data.tests) {
      const row = el(`<div class="file-row" data-f="${esc(t)}"><span class="fname">${esc(t)}</span></div>`);
      const btn = el(`<button class="btn xs">Run</button>`);
      btn.onclick = () => runTests(t);
      row.appendChild(btn);
      box.appendChild(row);
    }
    renderFailures(data.artifacts || []);
  } catch (err) {
    box.textContent = `tests error: ${err.message}`;
  }
}

function renderFailures(artifacts) {
  const card = document.getElementById("failures-card");
  const body = document.getElementById("failures-body");
  if (!artifacts.length) { card.hidden = true; return; }
  card.hidden = false;
  document.getElementById("failures-label").textContent = `Last failures (${artifacts.length})`;
  body.innerHTML = "";
  for (const a of artifacts) {
    const row = el(`<div class="fail-row"><span class="fn">${esc(a.name)}</span><span class="arts"></span></div>`);
    const arts = row.querySelector(".arts");
    if (a.xml) arts.appendChild(el(`<span class="btn xs" title="download not yet wired">.xml</span>`));
    if (a.png) arts.appendChild(el(`<span class="btn xs" title="download not yet wired">.png</span>`));
    body.appendChild(row);
  }
}
```

- [ ] **Step 2: Replace `runTests` (colored streaming into `#run-output`)**

Keep the POST + `EventSource` + `__END__:` wiring; change only how lines render.

```js
function termLine(text, cls) {
  const out = document.getElementById("run-output");
  out.appendChild(el(`<div${cls ? ` class="${cls}"` : ""}>${esc(text || " ")}</div>`));
  out.scrollTop = out.scrollHeight;
}

function classifyLine(line) {
  if (line.startsWith("$")) return "dim";
  if (/FAILED|Error|Exception|failed/.test(line)) return "red";
  if (/passed|\[100%\]|PASSED/.test(line)) return "green";
  return "";
}

async function runTests(target) {
  if (activeRun) { activeRun.close(); activeRun = null; }
  const out = document.getElementById("run-output");
  out.innerHTML = "";
  document.getElementById("exit-badge").textContent = "";
  document.querySelectorAll(".file-row").forEach((r) => r.classList.toggle("running", r.dataset.f === target));
  termLine(`$ pytest ${target}`, "dim");
  setRunButtonsDisabled(true);
  setTabDot("tests", "busy");
  let run_id;
  try {
    ({ run_id } = await fetchJSON("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, env: {} }),
    }));
  } catch (err) {
    termLine(`[error: ${err.message}]`, "red");
    setRunButtonsDisabled(false);
    setTabDot("tests", null);
    return;
  }
  const es = new EventSource(`/api/run/stream?id=${encodeURIComponent(run_id)}`);
  activeRun = es;
  es.onmessage = (e) => {
    if (e.data.startsWith("__END__:")) {
      const code = e.data.split(":")[1];
      termLine(`[exit ${code}]`, code === "0" ? "green" : "red");
      const badge = document.getElementById("exit-badge");
      badge.textContent = `exit ${code}`;
      badge.className = "exit-badge " + (code === "0" ? "ok" : "bad");
      es.close();
      activeRun = null;
      setTabDot("tests", null);
      document.querySelectorAll(".file-row").forEach((r) => r.classList.remove("running"));
      loadTests();
      return;
    }
    termLine(e.data, classifyLine(e.data));
  };
  es.onerror = () => {
    es.close();
    activeRun = null;
    setRunButtonsDisabled(false);
    setTabDot("tests", null);
  };
}
```

Also update `setRunButtonsDisabled` to include the `Run all` button:

```js
function setRunButtonsDisabled(disabled) {
  document.querySelectorAll("#tests button, #run-all").forEach((b) => { b.disabled = disabled; });
}
```

And wire `Run all` + the failures toggle once, near where the other one-time listeners are set (replacing the old `run-all` creation that lived inside `loadTests`):

```js
document.getElementById("run-all").onclick = () => runTests("all");
document.getElementById("failures-toggle").onclick = function () {
  const open = this.getAttribute("aria-expanded") === "true";
  this.setAttribute("aria-expanded", String(!open));
  document.getElementById("failures-body").hidden = open;
};
```

- [ ] **Step 3: Verify**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v` → PASS.
Manual: file list renders with per-file Run; Run all streams colored output ending in an `exit N` badge; the Tests tab shows the blue busy dot while streaming; failing runs reveal the collapsible "Last failures" section (labels only, no download).

- [ ] **Step 4: Commit**

```bash
git add studio/static/app.js
git commit -m "feat(studio): restyle Tests panel — file list, terminal, exit badge, failures"
```

---

## Task 4: Memory panel render

**Files:**
- Modify: `studio/static/app.js` (replace `loadMemory`, `loadStale`, `loadLint`; add `renderNote`, `memBanner`)
- Test: `studio/tests/test_server.py`

**Interfaces:**
- Consumes: `el`, `esc`, `fetchJSON` (existing); `/api/memory` → `{flows[], screens[], failures[], env}`; `/api/memory/note?path=`; `/api/memory/stale`; `/api/memory/lint`.
- Produces: none downstream.

- [ ] **Step 1: Replace `loadMemory` (groups sidebar + env chip) and add safe note render**

```js
let openNotePath = null;

async function loadMemory() {
  const box = document.getElementById("memory");
  try {
    const m = await fetchJSON("/api/memory");
    box.innerHTML = "";
    const groups = [["flows", "Flows"], ["screens", "Screens"], ["failures", "Failures"]];
    for (const [key, label] of groups) {
      box.appendChild(el(`<div class="mem-ghead"><span class="card-title">${esc(label)}</span></div>`));
      for (const name of m[key]) {
        const path = key + "/" + name + ".md";
        const btn = el(`<button class="mem-note"${path === openNotePath ? ' aria-current="true"' : ""}>${esc(name)}</button>`);
        btn.onclick = () => openNote(path);
        box.appendChild(btn);
      }
    }
    const chip = document.getElementById("env-chip");
    chip.hidden = !m.env;
  } catch (err) {
    box.textContent = `memory error: ${err.message}`;
  }
}

async function openNote(path) {
  openNotePath = path;
  document.querySelectorAll(".mem-note").forEach((b) => b.removeAttribute("aria-current"));
  try {
    const note = await fetchJSON(`/api/memory/note?path=${encodeURIComponent(path)}`);
    renderNote(path, note.content);
  } catch (err) {
    document.getElementById("note-view").innerHTML = `<div class="nv-body"><p class="plain">note error: ${esc(err.message)}</p></div>`;
  }
  loadMemory(); // repaint sidebar so the active note highlights
}

// Safe, line-based render — every fragment is escaped; never innerHTML raw content.
function renderNote(path, content) {
  const name = path.split("/").pop().replace(/\.md$/, "");
  const group = path.split("/")[0];
  const view = document.getElementById("note-view");
  view.innerHTML =
    `<div class="card-head nv-head"><span class="mono" style="font-size:12px;color:var(--muted)">${esc(name)}</span>` +
    `<span class="nv-tag">${esc(group)}</span></div><div class="nv-body" id="nv-body"></div>`;
  const body = document.getElementById("nv-body");
  for (const line of String(content).split("\n")) {
    if (line.indexOf("# ") === 0) { body.appendChild(el(`<h3>${esc(line.slice(2))}</h3>`)); continue; }
    if (line === "") { body.appendChild(el(`<div style="height:6px"></div>`)); continue; }
    const m = /^(Identifiers|Key assertion|Verified):(.*)$/.exec(line);
    if (m) { body.appendChild(el(`<p><span class="k">${esc(m[1])}:</span>${esc(m[2])}</p>`)); continue; }
    body.appendChild(el(`<p class="plain">${esc(line)}</p>`));
  }
}
```

- [ ] **Step 2: Replace `loadStale` / `loadLint` to write a banner**

```js
function memBanner(kind /* "ok"|"bad"|"warn" */, text) {
  document.getElementById("mem-banner").innerHTML = `<div class="result-banner ${kind}">${esc(text)}</div>`;
}

async function loadStale() {
  try {
    const r = await fetchJSON("/api/memory/stale");
    if (r.stale == null) return memBanner("warn", "stale check unavailable (memory scripts not found)");
    memBanner("warn", r.stale ? `Stale: ${r.stale}` : "Nothing stale");
  } catch (err) {
    memBanner("bad", `stale error: ${err.message}`);
  }
}

async function loadLint() {
  try {
    const r = await fetchJSON("/api/memory/lint");
    if (r.lint == null) return memBanner("warn", "lint unavailable (memory scripts not found)");
    memBanner(r.lint.ok ? "ok" : "bad", `${r.lint.ok ? "PASS" : "FAIL"} — ${r.lint.output || "(no output)"}`);
  } catch (err) {
    memBanner("bad", `lint error: ${err.message}`);
  }
}
```

(The `stale-btn` / `lint-btn` click listeners at the bottom of `app.js` are unchanged — they still call `loadStale` / `loadLint`.)

- [ ] **Step 3: Verify**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v` → PASS. Confirm the stale endpoint test (`test_server.py` line ~133, `stale is None`) is unaffected — this is a UI-only change.
Manual: Memory tab shows grouped notes; clicking a note renders it in the viewer with headings/label lines and highlights the active note; env chip shows only when `env.md` present; Check stale / Lint render a colored banner; Refresh re-fetches.

- [ ] **Step 4: Commit**

```bash
git add studio/static/app.js
git commit -m "feat(studio): restyle Memory panel — groups, safe note render, result banner"
```

---

## Task 5: Agent panel render

**Files:**
- Modify: `studio/static/app.js` (replace `renderStepper`, `logAppend` callers `appendProgress`/`appendResult`/`appendError`, `renderCard`/`renderForm`/`renderConfirm`/`renderReview`/`lockCard`, `pollAgentState`, `startJob`; add `convoCount`)
- Test: `studio/tests/test_server.py`

**Interfaces:**
- Consumes: `el`, `esc`, `sendReply`, `setTabDot`, the `STAGES` array + `seenRecordIds` + `dispatch` + `connectStream` (existing, **unchanged**); `/api/studio/*` endpoints.
- Produces: none downstream.
- **Contract:** reply payload shapes, `esc()` usage, `stage`-derived stepper, ~500-entry bound, dedupe-by-id, and status-aware attach indicator all preserved.

- [ ] **Step 1: Replace `renderStepper` (show/hide card + separators)**

```js
function renderStepper(current) {
  const card = document.getElementById("stepper-card");
  const box = document.getElementById("stepper");
  if (!current) { card.style.display = "none"; box.innerHTML = ""; return; }
  card.style.display = "";
  const seq = STAGES.includes(current) ? STAGES : STAGES.concat([current]);
  const idx = seq.indexOf(current);
  box.innerHTML = "";
  seq.forEach((s, i) => {
    const cls = i < idx ? "done" : (i === idx ? "active" : "");
    const mark = i < idx ? "✓ " : (i === idx ? "● " : "○ ");
    box.appendChild(el(`<span class="step ${cls}">${mark}${esc(s)}</span>`));
    if (i < seq.length - 1) box.appendChild(el(`<span class="step-sep ${i < idx ? "done" : ""}"></span>`));
  });
}
```

- [ ] **Step 2: Replace the log appenders + count**

Keep `logAppend` (it enforces the ~500 bound) as-is. Replace the three appenders and add a count updater:

```js
function convoCount() {
  const log = document.getElementById("agent-log");
  document.getElementById("convo-count").textContent = `${log.children.length} entries`;
}

function appendProgress(rec) {
  logAppend(el(
    `<div class="prog"><span class="pdot${rec.stage ? "" : " plain"}"></span>` +
    `<span class="ptext">${esc(rec.text)}${rec.stage ? `<span class="pstage">${esc(rec.stage)}</span>` : ""}</span></div>`));
  if (rec.stage) renderStepper(rec.stage);
  convoCount();
}

function appendResult(rec) {
  const green = rec.status === "green";
  logAppend(el(
    `<div class="result ${green ? "green" : "abandoned"}"><div class="rline"><span>${green ? "✓" : "—"}</span>` +
    `<span>${esc(rec.summary || rec.status)}</span></div>` +
    (rec.test_path ? `<div class="rpath">${esc(rec.test_path)}</div>` : "") + `</div>`));
  renderStepper(null);
  setTabDot("agent", null);
  convoCount();
}

function appendError(rec) {
  logAppend(el(`<div class="result abandoned"><div class="rline"><span>✕</span><span>${esc(rec.text)}</span></div></div>`));
  convoCount();
}
```

- [ ] **Step 3: Replace the card renderers (styled cards, same reply payloads)**

```js
const CARD_KIND_LABEL = { form: "Clarify", confirm: "Build step", review: "Review" };

function lockCard(card, summary) {
  card.querySelectorAll("input,button,textarea").forEach((n) => { n.disabled = true; });
  const head = card.querySelector(".mc-head");
  if (head && !head.querySelector(".mc-locked")) head.appendChild(el(`<span class="mc-locked">answered</span>`));
  card.querySelector(".mc-body").appendChild(el(`<div class="mc-locked-label">↳ ${esc(summary)}</div>`));
}

function renderCard(rec) {
  const label = rec.subtype === "permission" ? "Permission" : (CARD_KIND_LABEL[rec.kind] || rec.kind);
  const card = el(
    `<div class="msg-card"><div class="mc-head"><span class="mc-kind">${esc(label)}</span></div>` +
    `<div class="mc-body"><div class="mc-prompt">${esc(rec.prompt || "")}</div></div></div>`);
  const body = card.querySelector(".mc-body");
  if (rec.kind === "form") renderForm(rec, body);
  else if (rec.kind === "confirm") renderConfirm(rec, body);
  else if (rec.kind === "review") renderReview(rec, body);
  logAppend(card);
  setTabDot("agent", "alert");
  convoCount();
}

function renderForm(rec, body) {
  const fields = {};
  (rec.questions || []).forEach((q) => {
    const wrap = el(`<div class="field"><label>${esc(q.label)}</label></div>`);
    if (q.kind === "choice") {
      const choices = el(`<div class="segmented"></div>`);
      (q.options || []).forEach((opt) => {
        const seg = el(`<button type="button" class="seg" aria-pressed="false">${esc(opt)}</button>`);
        seg.dataset.value = opt;
        seg.onclick = () => {
          choices.querySelectorAll(".seg").forEach((s) => s.setAttribute("aria-pressed", "false"));
          seg.setAttribute("aria-pressed", "true");
        };
        choices.appendChild(seg);
      });
      wrap.appendChild(choices);
    } else {
      wrap.appendChild(el(`<input class="input" type="text" value="${esc(q.default || "")}" style="width:100%">`));
    }
    body.appendChild(wrap);
    fields[q.qid] = { q, wrap };
  });
  const submit = el(`<button class="btn btn-primary">Submit</button>`);
  submit.onclick = async () => {
    submit.disabled = true;
    try {
      const answers = {};
      for (const [qid, f] of Object.entries(fields)) {
        if (f.q.kind === "choice") {
          const pressed = f.wrap.querySelector('.seg[aria-pressed="true"]');
          answers[qid] = pressed ? pressed.dataset.value : "";
        } else {
          answers[qid] = f.wrap.querySelector("input").value;
        }
      }
      await sendReply({ reply_to: rec.id, answers });
      lockCard(submit.closest(".msg-card"), "answered");
    } catch (err) {
      body.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      submit.disabled = false;
    }
  };
  body.appendChild(submit);
}

function renderConfirm(rec, body) {
  const btn = el(`<button class="btn btn-primary">I've built &amp; installed</button>`);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "built" });
      lockCard(btn.closest(".msg-card"), "built");
    } catch (err) {
      body.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      btn.disabled = false;
    }
  };
  body.appendChild(btn);
}

function renderReview(rec, body) {
  if (rec.diff) {
    body.appendChild(el(`<div class="diff-label">Diff</div>`));
    body.appendChild(el(`<div class="diffbox">${esc(rec.diff)}</div>`));
  }
  (rec.test_files || []).forEach((f) => {
    body.appendChild(el(`<div class="diff-label">${esc(f.path)}</div>`));
    body.appendChild(el(`<div class="diffbox">${esc(f.content)}</div>`));
  });
  const note = el(`<div class="field" style="margin-top:10px" hidden><label>Rejection note (optional)</label><input class="input" type="text" style="width:100%" placeholder="What should be changed?"></div>`);
  const approve = el(`<button class="btn btn-success">Approve</button>`);
  const reject = el(`<button class="btn btn-danger">Reject</button>`);
  approve.onclick = async () => {
    approve.disabled = reject.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "approve" });
      lockCard(approve.closest(".msg-card"), "approved");
    } catch (err) {
      body.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      approve.disabled = reject.disabled = false;
    }
  };
  reject.onclick = async () => {
    if (note.hidden) { note.hidden = false; return; }
    approve.disabled = reject.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "reject", note: note.querySelector("input").value });
      lockCard(reject.closest(".msg-card"), "rejected");
    } catch (err) {
      body.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      approve.disabled = reject.disabled = false;
    }
  };
  const actions = el(`<div class="card-actions" style="margin-top:12px"></div>`);
  actions.appendChild(approve);
  actions.appendChild(reject);
  body.appendChild(actions);
  body.appendChild(note);
}
```

Note the changed argument: card renderers now receive the `.mc-body` element (not the whole card). The `lockCard` helper walks up via `.closest(".msg-card")`.

- [ ] **Step 4: Replace `pollAgentState` (dot + label) and `startJob` (styled queued line)**

```js
async function pollAgentState() {
  const box = document.getElementById("agent-status");
  const label = document.getElementById("attach-label");
  const set = (state, text) => { box.className = "attach " + state; label.textContent = text; };
  try {
    const s = await fetchJSON("/api/studio/state");
    const stale = s.heartbeat_ts && (Date.now() - Date.parse(s.heartbeat_ts) > 60000);
    if (!s.attached) { set("disconnected", "No agent connected — run /agentqa-studio in Claude Code"); setTabDot("agent", null); }
    else if (s.status === "waiting") {
      if (stale) { set("stale", "Agent waiting (no heartbeat — may have disconnected)"); setTabDot("agent", "alert"); }
      else { set("waiting", "Agent attached — waiting on you"); setTabDot("agent", "alert"); }
    } else if (s.status === "running") { set("running", "Agent working…"); setTabDot("agent", "busy"); }
    else { set("idle", "Agent attached — idle"); setTabDot("agent", null); }
  } catch (err) {
    set("disconnected", `agent state error: ${err.message}`);
  }
}

async function startJob() {
  const ideaEl = document.getElementById("job-idea");
  const idea = ideaEl.value.trim();
  if (!idea) return;
  const btn = document.getElementById("job-start");
  btn.disabled = true;
  try {
    await fetchJSON("/api/studio/job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flow_idea: idea }),
    });
    ideaEl.value = "";
    logAppend(el(`<div class="prog"><span class="pdot plain"></span><span class="ptext muted">▸ queued: ${esc(idea)}</span></div>`));
    convoCount();
  } catch (err) {
    appendError({ text: err.message });
  } finally {
    btn.disabled = false;
  }
}
```

Add Enter-to-submit for the job input next to the existing `job-start` listener:

```js
document.getElementById("job-idea").addEventListener("keydown", (e) => { if (e.key === "Enter") startJob(); });
```

- [ ] **Step 5: Verify**

Run: `.devvenv/bin/pytest studio/tests/test_server.py -v` → PASS.
Manual (agent attached via `/agentqa-studio` in an app repo): status line shows the right dot/label per state; the Agent tab dot is amber (pulse) while a card waits, blue while working, gone when idle; stepper lights per `stage` and hides on result; progress/result/error render in the new styles; each card type submits with the **unchanged** payloads (`{answers}` / `{decision:"built"}` / `{decision:"approve"}` / `{decision:"reject", note}`) and locks with a `↳` marker; reconnect still dedupes (no doubled entries).

- [ ] **Step 6: Commit**

```bash
git add studio/static/app.js
git commit -m "feat(studio): restyle Agent panel — stepper, conversation, cards, attach"
```

---

## Task 6: Full verification + finish branch

**Files:** none (verification only)

- [ ] **Step 1: Asset + full studio test suite green**

```
.devvenv/bin/pytest studio/tests/test_server.py -v
.devvenv/bin/pytest studio/tests/ -v
```
Expected: all PASS (static-only changes; server/module tests unaffected).

- [ ] **Step 2: End-to-end manual smoke**

Launch against an app repo that has `.agentqa/`:
`.devvenv/bin/python -m studio.server --repo <that repo> --port 7332 --open`

Walk the checklist: (a) all four tabs render and switch; (b) theme toggle flips + persists, both themes legible, no sideways page scroll at narrow widths; (c) Rig cards + summary + red dot on failure; (d) Tests stream colored output + exit badge + failures section + busy dot; (e) Memory notes open + banner + env chip; (f) attach a real agent and run one job — answer a clarify card, a build confirm, and a review approve/reject; confirm the reply reaches the agent and the card locks; (g) kill/reconnect the SSE (reload) and confirm the transcript replays without duplicates.

- [ ] **Step 3: Behavior-contract spot check**

Grep to confirm the invariants survived the port:
```
grep -c "esc(" studio/static/app.js          # every dynamic string still escaped
grep -n "seenRecordIds" studio/static/app.js  # dedupe-by-id intact
grep -n "connectStream" studio/static/app.js  # smoke invariant
grep -n "\.stepper" studio/static/style.css   # smoke invariant
```

- [ ] **Step 4: Update the mockup-preview note (optional cleanup)**

The `preview` chip existed only in the mockup, not the ported `index.html` — confirm it is absent from the real file. No action if already absent.

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch to decide how to integrate `studio-ui-redesign` (the spec was committed here earlier). Do not merge/push without the user's go-ahead.

---

## Self-Review

**Spec coverage:** Every spec section maps to a task — visual system + theme + shell → Task 1; Rig → Task 2; Tests (incl. flagged inert `.xml`/`.png` labels) → Task 3; Memory (safe markdown render, banner) → Task 4; Agent (attach, stepper, four card types, bounded log, dedupe) → Task 5; testing + manual smoke + contract check → Task 6. The "out of scope" items (server changes, artifact download, new config fields) are honored (labels only; no server edits).

**Placeholder scan:** No TBD/TODO; every code step is concrete. Manual verification steps are explicit checklists (a UI restyle has no unit tests for rendered output; the asset smoke test + the manual checklist + the contract grep are the verification, stated as such).

**Type/name consistency:** IDs are stable and identical across HTML and JS (`rig`, `tests`, `run-output`, `memory`, `note-view`, `agent-status`, `stepper`, `agent-log`, `job-idea`, `job-start`); new helpers (`setTabDot`, `renderRigSummary`, `renderFailures`, `termLine`, `classifyLine`, `renderNote`, `memBanner`, `convoCount`, `showTab`, `SVG_CHECK`, `SVG_WARN`) are each defined once and referenced consistently; card renderers uniformly take `.mc-body` and `lockCard` climbs via `.closest(".msg-card")`; reply payloads match the preserved `sendReply` contract verbatim.
