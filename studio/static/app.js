// studio/static/app.js — vanilla, no build. Renders the three M1 panels.
async function fetchJSON(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(body && body.error ? text(body.error) : `HTTP ${r.status}`);
  }
  return body;
}

// Every string the UI paints goes through here first. The mailbox is written by
// an agent, not by this code, so any field can arrive as an object — and
// `String(obj)` renders the useless "[object Object]". Objects become compact
// JSON instead: still wrong-looking, but it names the field that misbehaved.
function text(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    try { return JSON.stringify(v); } catch (_) { return ""; }
  }
  return String(v);
}

function esc(s) {
  return text(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// A choice option is either a bare string or a {label, value} pair (Studio
// Protocol v1 allows both). The button shows the label; the reply carries the
// value — conflating them is what shipped "[object Object]" back to the agent.
function optionLabel(opt) {
  if (opt && typeof opt === "object" && !Array.isArray(opt)) {
    if (opt.label !== undefined && opt.label !== null) return text(opt.label);
    if (opt.value !== undefined && opt.value !== null) return text(opt.value);
  }
  return text(opt);
}

function optionValue(opt) {
  if (opt && typeof opt === "object" && !Array.isArray(opt)) {
    if (opt.value !== undefined && opt.value !== null) return text(opt.value);
    if (opt.label !== undefined && opt.label !== null) return text(opt.label);
  }
  return text(opt);
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>';
const SVG_WARN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>';

let openNotePath = null;

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

async function loadConfig() {
  const box = document.getElementById("config");
  try {
    const c = await fetchJSON("/api/config");
    box.textContent = `${text(c.platform)} · ${text(c.app_id)} · ` +
      `build:${text(c.build_policy)} · appium:${text(c.appium_port)}`;
  } catch (err) {
    box.textContent = `config error: ${err.message}`;
  }
}

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

function setRunButtonsDisabled(disabled) {
  document.querySelectorAll("#tests button, #run-all").forEach((b) => { b.disabled = disabled; });
}

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

let activeRun = null;

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
  const badge = document.getElementById("exit-badge"); badge.textContent = ""; badge.className = "exit-badge";
  document.querySelectorAll(".file-row").forEach((r) => r.classList.toggle("running", r.dataset.f === target));
  termLine(`$ pytest ${text(target)}`, "dim");
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
      setRunButtonsDisabled(false);
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
  for (const line of text(content).split("\n")) {
    if (line.indexOf("# ") === 0) { body.appendChild(el(`<h3>${esc(line.slice(2))}</h3>`)); continue; }
    if (line === "") { body.appendChild(el(`<div style="height:6px"></div>`)); continue; }
    const m = /^(Identifiers|Key assertion|Verified):(.*)$/.exec(line);
    if (m) { body.appendChild(el(`<p><span class="k">${esc(m[1])}:</span>${esc(m[2])}</p>`)); continue; }
    body.appendChild(el(`<p class="plain">${esc(line)}</p>`));
  }
}

function memBanner(kind /* "ok"|"bad"|"warn" */, text) {
  document.getElementById("mem-banner").innerHTML = `<div class="result-banner ${kind}">${esc(text)}</div>`;
}

async function loadStale() {
  try {
    const r = await fetchJSON("/api/memory/stale");
    if (r.stale == null) return memBanner("warn", "stale check unavailable (memory scripts not found)");
    memBanner("warn", r.stale ? `Stale: ${text(r.stale)}` : "Nothing stale");
  } catch (err) {
    memBanner("bad", `stale error: ${err.message}`);
  }
}

async function loadLint() {
  try {
    const r = await fetchJSON("/api/memory/lint");
    if (r.lint == null) return memBanner("warn", "lint unavailable (memory scripts not found)");
    memBanner(r.lint.ok ? "ok" : "bad", `${r.lint.ok ? "PASS" : "FAIL"} — ${text(r.lint.output) || "(no output)"}`);
  } catch (err) {
    memBanner("bad", `lint error: ${err.message}`);
  }
}

document.querySelectorAll("[data-refresh]").forEach((b) => {
  b.onclick = () => ({ rig: loadRig, memory: loadMemory }[b.dataset.refresh]());
});
document.getElementById("stale-btn").onclick = loadStale;
document.getElementById("lint-btn").onclick = loadLint;
document.getElementById("run-all").onclick = () => runTests("all");
document.getElementById("failures-toggle").onclick = function () {
  const open = this.getAttribute("aria-expanded") === "true";
  this.setAttribute("aria-expanded", String(!open));
  document.getElementById("failures-body").hidden = open;
};

loadConfig();
loadRig();
loadTests();
loadMemory();

// ---- Panel 3: Agent conversation ---------------------------------------
const STAGES = ["map", "clarify", "explore", "identifiers", "build",
                "verify", "write", "green", "review", "capture"];
const seenRecordIds = new Set();

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

const STICK_THRESHOLD_PX = 48;

// Pure: is the reader parked at the newest entry? Only then may new content pull
// the box down — someone scrolled up is reading history and yanking them to the
// bottom loses their place. The threshold absorbs sub-pixel scroll positions and
// keeps "following" from breaking on a stray wheel tick.
function isAtBottom(scrollTop, clientHeight, scrollHeight) {
  return scrollHeight - scrollTop - clientHeight <= STICK_THRESHOLD_PX;
}

function scrollToLatest() {
  const log = document.getElementById("agent-log");
  log.scrollTop = log.scrollHeight;
  document.getElementById("jump-latest").hidden = true;
}

function logAppend(node) {
  const log = document.getElementById("agent-log");
  // Measured before the append, or the new node's own height already counts as
  // "scrolled away from the bottom" and stick would never hold.
  const stick = isAtBottom(log.scrollTop, log.clientHeight, log.scrollHeight);
  log.appendChild(node);
  // Trimming from the top shifts everything up under a reader who is scrolled
  // into history; hold their position by the height the removal took away.
  while (log.children.length > 500) {
    const gone = log.firstElementChild.getBoundingClientRect().height;
    log.removeChild(log.firstElementChild);
    if (!stick) log.scrollTop = Math.max(0, log.scrollTop - gone);
  }
  if (stick) scrollToLatest();
  else document.getElementById("jump-latest").hidden = false;
}

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

async function sendReply(payload) {
  await fetchJSON("/api/studio/reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// `clarify` and `ask` share kind "form", so the kind alone cannot name a card —
// an `ask` (a permission prompt / OTP / springboard pop-up the phone put up) read
// as "Clarify" and looked like a stray requirements question. Subtype wins; kind
// stays as the fallback for a subtype the UI has not learned yet.
const CARD_SUBTYPE_LABEL = { clarify: "Clarify", ask: "System dialog", build: "Build step", review: "Review" };
const CARD_KIND_LABEL = { form: "Clarify", confirm: "Build step", review: "Review" };

function cardLabel(rec) {
  return CARD_SUBTYPE_LABEL[rec.subtype] || CARD_KIND_LABEL[rec.kind] || rec.kind;
}

function lockCard(card, summary) {
  card.querySelectorAll("input,button,textarea").forEach((n) => { n.disabled = true; });
  const head = card.querySelector(".mc-head");
  if (head && !head.querySelector(".mc-locked")) head.appendChild(el(`<span class="mc-locked">answered</span>`));
  card.querySelector(".mc-body").appendChild(el(`<div class="mc-locked-label">↳ ${esc(summary)}</div>`));
}

function renderCard(rec) {
  const label = cardLabel(rec);
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
        const seg = el(`<button type="button" class="seg" aria-pressed="false">${esc(optionLabel(opt))}</button>`);
        seg.dataset.value = optionValue(opt);
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

function dispatch(rec) {
  if (rec && rec.id) {
    if (seenRecordIds.has(rec.id)) return;   // reconnect replays the outbox; render each record once
    seenRecordIds.add(rec.id);
  }
  if (rec.type === "progress") return appendProgress(rec);
  if (rec.type === "question") return renderCard(rec);
  if (rec.type === "result") return appendResult(rec);
  if (rec.type === "error") return appendError(rec);
}

let agentStream = null;

// A new connector archives the mailbox on attach, and the daemon says so on the
// stream. Everything on screen belongs to the archived session — including cards
// whose agent is gone, which would silently do nothing if clicked — so drop the
// lot. This arrives ahead of the new session's records on the same stream, so
// there is no window where a reset wipes messages that already belong to it.
function resetConversation() {
  const log = document.getElementById("agent-log");
  log.innerHTML = "";
  seenRecordIds.clear();
  renderStepper(null);
  document.getElementById("jump-latest").hidden = true;
  setTabDot("agent", null);
  logAppend(el(`<div class="prog"><span class="pdot plain"></span>` +
    `<span class="ptext muted">▸ new agent session attached — earlier messages archived</span></div>`));
  convoCount();
}

function connectStream() {
  const es = new EventSource("/api/studio/stream");
  agentStream = es;
  es.onmessage = (e) => {
    let rec;
    try { rec = JSON.parse(e.data); } catch (_) { return; }
    dispatch(rec);
  };
  es.addEventListener("session", resetConversation);
  es.onerror = () => { /* browser auto-reconnects; the outbox replays on reconnect */ };
}

const HEARTBEAT_STALE_MS = 60000;

// Pure: how the attach badge should read. `attached` is sticky — the agent sets it
// on attach and only clears it on a clean detach — so a session that just ended
// still looks attached. The heartbeat is what proves someone is home, but it is
// only bumped by studio-wait.py's poll loop, which backs `idle` and `waiting` and
// NOT `running` (a working agent is off driving the device for minutes with
// nothing touching state.json). So staleness is only meaningful in the first two.
function attachView(s, now) {
  if (!s.attached) {
    return { state: "disconnected", text: "No agent connected — run /agentqa-studio in Claude Code", dot: null };
  }
  if (s.status === "running") return { state: "running", text: "Agent working…", dot: "busy" };
  if (s.heartbeat_ts && now - Date.parse(s.heartbeat_ts) > HEARTBEAT_STALE_MS) {
    return {
      state: "stale",
      text: s.status === "waiting"
        ? "Agent waiting (no heartbeat — may have disconnected)"
        : "Agent went away (no heartbeat) — re-run /agentqa-studio to pick up queued jobs",
      dot: "alert",
    };
  }
  if (s.status === "waiting") return { state: "waiting", text: "Agent attached — waiting on you", dot: "alert" };
  return { state: "idle", text: "Agent attached — idle", dot: null };
}

// True when an agent is demonstrably alive right now — used to warn at queue time.
function agentIsLive(s) {
  const state = attachView(s, Date.now()).state;
  return state !== "disconnected" && state !== "stale";
}

async function pollAgentState() {
  const box = document.getElementById("agent-status");
  const label = document.getElementById("attach-label");
  const set = (state, text) => { box.className = "attach " + state; label.textContent = text; };
  try {
    const v = attachView(await fetchJSON("/api/studio/state"), Date.now());
    set(v.state, v.text);
    setTabDot("agent", v.dot);
  } catch (err) {
    set("disconnected", `agent state error: ${err.message}`);
  }
}

// ---- Requirements upload -------------------------------------------------
// A requirements doc is an *intent* artifact — the same thing `docs:` points at
// in .agentqa/config.yml — handed to one job instead of committed to the repo.
// It travels as a pointer: the job record carries {name, path, chars} and the
// agent opens the file, so a long spec never bloats inbox.jsonl.
let attachedRequirements = null;

// Pure: what to call a job whose idea box was left empty. A requirements file
// is usually titled with the thing it describes, so its first heading is a
// better job name than the filename, and the filename beats nothing at all.
function deriveIdea(idea, filename, content) {
  const typed = (idea || "").trim();
  if (typed) return typed;
  const heading = (text(content).match(/^\s*#{1,3}\s+(.+?)\s*$/m) || [])[1];
  if (heading) return heading.trim();
  return text(filename).replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim();
}

function attachError(msg) {
  const box = document.getElementById("attach-error");
  box.textContent = text(msg);
  box.hidden = !msg;
}

function paintAttachment() {
  const chip = document.getElementById("req-chip");
  if (!attachedRequirements) {
    chip.hidden = true;
    document.getElementById("attach-hint").hidden = false;
    return;
  }
  document.getElementById("req-name").textContent = attachedRequirements.name;
  document.getElementById("req-size").textContent =
    `${Math.max(1, Math.round(attachedRequirements.chars / 1000))} KB`;
  chip.hidden = false;
  document.getElementById("attach-hint").hidden = true;
}

async function attachFile(file) {
  if (!file) return;
  attachError("");
  let content;
  try {
    content = await file.text();
  } catch (err) {
    return attachError(`Could not read that file: ${err.message}`);
  }
  try {
    // The daemon re-checks the type and size; it owns the refusal message so
    // the browser and a direct POST get the same answer.
    const stored = await fetchJSON("/api/studio/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, content }),
    });
    attachedRequirements = stored;
    attachedRequirements.text = content;
    paintAttachment();
  } catch (err) {
    attachedRequirements = null;
    paintAttachment();
    attachError(err.message);
  }
}

async function startJob() {
  const ideaEl = document.getElementById("job-idea");
  const idea = deriveIdea(
    ideaEl.value,
    attachedRequirements ? attachedRequirements.name : "",
    attachedRequirements ? attachedRequirements.text : "");
  if (!idea) return;
  const btn = document.getElementById("job-start");
  btn.disabled = true;
  const req = attachedRequirements
    ? { name: attachedRequirements.name, path: attachedRequirements.path,
        chars: attachedRequirements.chars }
    : null;
  try {
    await fetchJSON("/api/studio/job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flow_idea: idea, requirements: req }),
    });
    ideaEl.value = "";
    attachedRequirements = null;
    paintAttachment();
    attachError("");
    logAppend(el(`<div class="prog"><span class="pdot plain"></span><span class="ptext muted">▸ queued: ${esc(idea)}` +
      (req ? ` <span class="pstage">${esc(req.name)}</span>` : "") + `</span></div>`));
    // The mailbox accepts a job whether or not anyone is listening. Say so, or the
    // job just sits at "queued" and reads as an agent that is quietly working.
    if (!agentIsLive(await fetchJSON("/api/studio/state"))) {
      appendError({ text: "Queued, but no live agent is watching the mailbox — run /agentqa-studio in Claude Code and it will pick this job up." });
    }
    convoCount();
  } catch (err) {
    appendError({ text: err.message });
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("job-start").onclick = startJob;
document.getElementById("job-idea").addEventListener("keydown", (e) => { if (e.key === "Enter") startJob(); });
document.getElementById("req-file").addEventListener("change", function () {
  attachFile(this.files[0]);
  this.value = "";       // so re-picking the same file fires change again
});
document.getElementById("req-remove").onclick = () => {
  attachedRequirements = null;
  paintAttachment();
  attachError("");
};
// Dropping the spec straight onto the card is how most people will do this.
const jobCard = document.getElementById("job-card");
["dragenter", "dragover"].forEach((ev) => jobCard.addEventListener(ev, (e) => {
  e.preventDefault();
  jobCard.classList.add("dropping");
}));
["dragleave", "drop"].forEach((ev) => jobCard.addEventListener(ev, (e) => {
  e.preventDefault();
  if (ev === "dragleave" && jobCard.contains(e.relatedTarget)) return;
  jobCard.classList.remove("dropping");
}));
jobCard.addEventListener("drop", (e) => {
  if (e.dataTransfer && e.dataTransfer.files.length) attachFile(e.dataTransfer.files[0]);
});

// ---- Requirements guide -------------------------------------------------
// The template in index.html is the single copy: copied and downloaded from the
// same node the dialog shows, so the three can never drift apart.
function requirementsTemplate() {
  return document.getElementById("req-template").textContent;
}

document.getElementById("guide-open").onclick = () => document.getElementById("guide-dialog").showModal();
document.getElementById("guide-copy").onclick = async function () {
  try {
    await navigator.clipboard.writeText(requirementsTemplate());
    this.textContent = "Copied";
  } catch (err) {
    this.textContent = "Copy failed — select the text";
  }
  setTimeout(() => { this.textContent = "Copy template"; }, 1800);
};
document.getElementById("guide-download").onclick = () => {
  const blob = new Blob([requirementsTemplate()], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "requirements-template.md";
  a.click();
  URL.revokeObjectURL(a.href);
};
document.getElementById("jump-latest").onclick = scrollToLatest;
// Scrolling back down yourself dismisses the pill — it only ever means "there is
// something below you", never "click here to scroll".
document.getElementById("agent-log").addEventListener("scroll", function () {
  if (isAtBottom(this.scrollTop, this.clientHeight, this.scrollHeight)) {
    document.getElementById("jump-latest").hidden = true;
  }
});
pollAgentState();
let agentPoll = setInterval(pollAgentState, 4000);
connectStream();

// ---- Stop the daemon ----------------------------------------------------
// Pure: what the confirm dialog owes the user before the daemon dies. Stopping
// Studio only stops the browser bridge — the agent talks to the mailbox files
// directly and a pytest run is its own child process, so both outlive the
// server with nobody left watching them. `attached` is what says an agent is
// home; a stale state.json can read "running" long after one walked away.
function shutdownWarnings(state, runActive) {
  const out = [];
  const agent = state && state.attached;
  if (agent && state.status === "running") {
    out.push("The agent is running a job — it keeps going in Claude Code.");
  }
  if (agent && state.status === "waiting") {
    out.push("The agent is waiting on your answer — you won't be able to answer once Studio stops.");
  }
  if (runActive) {
    out.push("A pytest run is streaming — the test process is left running.");
  }
  return out;
}

async function openStopDialog() {
  let state = {};
  // Fresh, not the 4s poll's last value. A state we cannot read is no reason to
  // stand between the user and their own stop button — warn about nothing.
  try { state = await fetchJSON("/api/studio/state"); } catch (err) { state = {}; }
  const box = document.getElementById("stop-warnings");
  box.innerHTML = "";
  for (const w of shutdownWarnings(state, activeRun !== null)) {
    box.appendChild(el(`<div class="dlg-warn">${esc(w)}</div>`));
  }
  document.getElementById("stop-dialog").showModal();
}

async function stopServer() {
  try {
    await fetchJSON("/api/shutdown", { method: "POST" });
  } catch (err) {
    // The connection dropping as the socket dies is this request's normal
    // shape, not a failure — the button said stop, so report stopped.
  }
  if (activeRun) { activeRun.close(); activeRun = null; }
  if (agentStream) { agentStream.close(); agentStream = null; }
  // Otherwise the tab reconnects to a dead server forever and floods the console.
  clearInterval(agentPoll);
  document.body.appendChild(el(
    `<div class="stopped"><div class="stopped-card">` +
    `<div class="stopped-title">Studio stopped</div>` +
    `<div class="stopped-hint">Run <code>agentqa-studio</code> to start it again.</div>` +
    `</div></div>`));
}

document.getElementById("stop-server").onclick = openStopDialog;
document.getElementById("stop-dialog").addEventListener("close", function () {
  if (this.returnValue === "stop") stopServer();
});
