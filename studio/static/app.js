// studio/static/app.js — vanilla, no build. Renders the three M1 panels.
async function fetchJSON(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(body && body.error ? body.error : `HTTP ${r.status}`);
  }
  return body;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

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

async function loadConfig() {
  const box = document.getElementById("config");
  try {
    const c = await fetchJSON("/api/config");
    box.textContent =
      `${c.platform} · ${c.app_id} · build:${c.build_policy} · appium:${c.appium_port}`;
  } catch (err) {
    box.textContent = `config error: ${err.message}`;
  }
}

async function loadRig() {
  const box = document.getElementById("rig");
  try {
    const r = await fetchJSON("/api/rig");
    box.innerHTML = "";
    const labels = { simulator: "Simulator", app_installed: "App", appium: "Appium", codegraph: "CodeGraph" };
    for (const key of Object.keys(labels)) {
      const ok = r[key];
      box.appendChild(el(`<span class="dot ${ok ? "ok" : "bad"}">${ok ? "●" : "○"} ${labels[key]}</span>`));
    }
  } catch (err) {
    box.textContent = `rig error: ${err.message}`;
  }
}

function setRunButtonsDisabled(disabled) {
  document.querySelectorAll("#tests button").forEach((b) => { b.disabled = disabled; });
}

async function loadTests() {
  const box = document.getElementById("tests");
  try {
    const data = await fetchJSON("/api/tests");
    box.innerHTML = "";
    box.appendChild(el(`<button id="run-all">Run all</button>`));
    document.getElementById("run-all").onclick = () => runTests("all");
    for (const t of data.tests) {
      const row = el(`<div class="test-row"><span>${esc(t)}</span></div>`);
      const btn = el(`<button>Run</button>`);
      btn.onclick = () => runTests(t);
      row.appendChild(btn);
      box.appendChild(row);
    }
    if (data.artifacts.length) {
      box.appendChild(el(`<div class="muted">Last failures: ${data.artifacts.map((a) => esc(a.name)).join(", ")}</div>`));
    }
  } catch (err) {
    box.textContent = `tests error: ${err.message}`;
  }
}

let activeRun = null;

async function runTests(target) {
  if (activeRun) { activeRun.close(); activeRun = null; }
  const out = document.getElementById("run-output");
  out.textContent = `$ pytest ${target}\n`;
  setRunButtonsDisabled(true);
  let run_id;
  try {
    ({ run_id } = await fetchJSON("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, env: {} }),
    }));
  } catch (err) {
    out.textContent += `\n[error: ${err.message}]\n`;
    setRunButtonsDisabled(false);
    return;
  }
  const es = new EventSource(`/api/run/stream?id=${encodeURIComponent(run_id)}`);
  activeRun = es;
  es.onmessage = (e) => {
    if (e.data.startsWith("__END__:")) {
      out.textContent += `\n[exit ${e.data.split(":")[1]}]\n`;
      es.close();
      activeRun = null;
      loadTests();
      return;
    }
    out.textContent += e.data + "\n";
    out.scrollTop = out.scrollHeight;
  };
  es.onerror = () => {
    es.close();
    activeRun = null;
    setRunButtonsDisabled(false);
  };
}

async function loadMemory() {
  const box = document.getElementById("memory");
  try {
    const m = await fetchJSON("/api/memory");
    box.innerHTML = "";
    for (const kind of ["flows", "screens", "failures"]) {
      const group = el(`<div class="mem-group"><strong>${kind}</strong></div>`);
      for (const name of m[kind]) {
        const a = el(`<a href="#">${esc(name)}</a>`);
        a.onclick = async (ev) => {
          ev.preventDefault();
          try {
            const note = await fetchJSON(
              `/api/memory/note?path=${encodeURIComponent(kind + "/" + name + ".md")}`);
            document.getElementById("note-view").textContent = note.content;
          } catch (err) {
            document.getElementById("note-view").textContent = `note error: ${err.message}`;
          }
        };
        group.appendChild(a);
      }
      box.appendChild(group);
    }
    box.appendChild(el(`<div class="muted">env.md: ${m.env ? "present" : "absent"}</div>`));
  } catch (err) {
    box.textContent = `memory error: ${err.message}`;
  }
}

async function loadStale() {
  const box = document.getElementById("note-view");
  try {
    const r = await fetchJSON("/api/memory/stale");
    box.textContent = r.stale == null
      ? "stale check unavailable (memory scripts not found)"
      : (r.stale || "(nothing stale)");
  } catch (err) {
    box.textContent = `stale error: ${err.message}`;
  }
}

async function loadLint() {
  const health = document.getElementById("mem-health");
  const box = document.getElementById("note-view");
  try {
    const r = await fetchJSON("/api/memory/lint");
    if (r.lint == null) {
      health.textContent = "lint: unavailable";
      health.className = "muted";
      box.textContent = "lint unavailable (memory scripts not found)";
      return;
    }
    health.textContent = r.lint.ok ? "lint: OK" : "lint: FAIL";
    health.className = r.lint.ok ? "dot ok" : "dot bad";
    box.textContent = r.lint.output || "(no output)";
  } catch (err) {
    box.textContent = `lint error: ${err.message}`;
  }
}

document.querySelectorAll("[data-refresh]").forEach((b) => {
  b.onclick = () => ({ rig: loadRig, memory: loadMemory }[b.dataset.refresh]());
});
document.getElementById("stale-btn").onclick = loadStale;
document.getElementById("lint-btn").onclick = loadLint;

loadConfig();
loadRig();
loadTests();
loadMemory();

// ---- Panel 3: Agent conversation ---------------------------------------
const STAGES = ["map", "clarify", "explore", "identifiers", "build",
                "verify", "write", "green", "review", "capture"];
const seenRecordIds = new Set();

function renderStepper(current) {
  const box = document.getElementById("stepper");
  const seq = STAGES.includes(current) ? STAGES : STAGES.concat([current]);
  const idx = seq.indexOf(current);
  box.innerHTML = "";
  seq.forEach((s, i) => {
    const cls = i < idx ? "done" : (i === idx ? "active" : "");
    box.appendChild(el(`<span class="step ${cls}">${esc(s)}</span>`));
  });
}

function logAppend(node) {
  const log = document.getElementById("agent-log");
  log.appendChild(node);
  while (log.children.length > 500) log.removeChild(log.firstElementChild);
  log.scrollTop = log.scrollHeight;
}

function appendProgress(rec) {
  logAppend(el(`<div class="msg">${esc(rec.text)}</div>`));
  if (rec.stage) renderStepper(rec.stage);
}

function appendResult(rec) {
  const cls = rec.status === "green" ? "ok" : "bad";
  const path = rec.test_path ? ` — ${esc(rec.test_path)}` : "";
  logAppend(el(`<div class="msg card"><strong class="dot ${cls}">${esc(rec.status)}</strong> ${esc(rec.summary || "")}${path}</div>`));
}

function appendError(rec) {
  logAppend(el(`<div class="msg card"><strong class="dot bad">error</strong> ${esc(rec.text)}</div>`));
}

async function sendReply(payload) {
  await fetchJSON("/api/studio/reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function lockCard(card, summary) {
  card.querySelectorAll("input,button,textarea").forEach((n) => { n.disabled = true; });
  card.appendChild(el(`<div class="muted locked">↳ ${esc(summary)}</div>`));
}

function renderForm(rec, card) {
  const fields = {};
  (rec.questions || []).forEach((q) => {
    const wrap = el(`<div class="field"><label>${esc(q.label)}</label></div>`);
    if (q.kind === "choice") {
      const choices = el(`<div class="choices"></div>`);
      (q.options || []).forEach((opt) => {
        choices.appendChild(el(
          `<label class="opt"><input type="radio" name="${esc(rec.id + q.qid)}" value="${esc(opt)}"> ${esc(opt)}</label>`));
      });
      wrap.appendChild(choices);
    } else {
      wrap.appendChild(el(`<input type="text" value="${esc(q.default || "")}">`));
    }
    card.appendChild(wrap);
    fields[q.qid] = { q, wrap };
  });
  const submit = el(`<button>Submit</button>`);
  submit.onclick = async () => {
    submit.disabled = true;
    try {
      const answers = {};
      for (const [qid, f] of Object.entries(fields)) {
        if (f.q.kind === "choice") {
          const checked = f.wrap.querySelector("input:checked");
          answers[qid] = checked ? checked.value : "";
        } else {
          answers[qid] = f.wrap.querySelector("input").value;
        }
      }
      await sendReply({ reply_to: rec.id, answers });
      lockCard(card, "answered");
    } catch (err) {
      card.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      submit.disabled = false;
    }
  };
  card.appendChild(submit);
}

function renderConfirm(rec, card) {
  const btn = el(`<button>I've built &amp; installed</button>`);
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "built" });
      lockCard(card, "built");
    } catch (err) {
      card.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      btn.disabled = false;
    }
  };
  card.appendChild(btn);
}

function renderReview(rec, card) {
  card.appendChild(el(`<pre class="diffbox">${esc(rec.diff || "")}</pre>`));
  (rec.test_files || []).forEach((f) => {
    card.appendChild(el(`<div class="muted">${esc(f.path)}</div>`));
    card.appendChild(el(`<pre class="diffbox">${esc(f.content)}</pre>`));
  });
  const note = el(`<textarea placeholder="reason (if rejecting)"></textarea>`);
  note.style.display = "none";
  const approve = el(`<button>Approve</button>`);
  const reject = el(`<button>Reject</button>`);
  approve.onclick = async () => {
    approve.disabled = reject.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "approve" });
      lockCard(card, "approved");
    } catch (err) {
      card.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      approve.disabled = reject.disabled = false;
    }
  };
  reject.onclick = async () => {
    if (note.style.display === "none") { note.style.display = "block"; return; }
    approve.disabled = reject.disabled = true;
    try {
      await sendReply({ reply_to: rec.id, decision: "reject", note: note.value });
      lockCard(card, "rejected");
    } catch (err) {
      card.appendChild(el(`<div class="muted">reply failed: ${esc(err.message)}</div>`));
      approve.disabled = reject.disabled = false;
    }
  };
  const actions = el(`<div class="card-actions"></div>`);
  actions.appendChild(approve);
  actions.appendChild(reject);
  card.appendChild(note);
  card.appendChild(actions);
}

function renderCard(rec) {
  const card = el(`<div class="msg card"></div>`);
  card.appendChild(el(`<div class="prompt">${esc(rec.prompt || "")}</div>`));
  if (rec.kind === "form") renderForm(rec, card);
  else if (rec.kind === "confirm") renderConfirm(rec, card);
  else if (rec.kind === "review") renderReview(rec, card);
  logAppend(card);
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

function connectStream() {
  const es = new EventSource("/api/studio/stream");
  es.onmessage = (e) => {
    let rec;
    try { rec = JSON.parse(e.data); } catch (_) { return; }
    dispatch(rec);
  };
  es.onerror = () => { /* browser auto-reconnects; the outbox replays on reconnect */ };
}

async function pollAgentState() {
  const box = document.getElementById("agent-status");
  try {
    const s = await fetchJSON("/api/studio/state");
    const stale = s.heartbeat_ts && (Date.now() - Date.parse(s.heartbeat_ts) > 60000);
    if (!s.attached) {
      box.textContent = "No agent connected — run /agentqa-studio in Claude Code";
      box.className = "muted";
    } else if (s.status === "waiting") {
      box.textContent = stale
        ? "Agent waiting (no heartbeat — may have disconnected)"
        : "Agent attached — waiting on you";
      box.className = stale ? "dot bad" : "dot ok";
    } else if (s.status === "running") {
      box.textContent = "Agent working…";
      box.className = "dot ok";
    } else {
      box.textContent = "Agent attached — idle";
      box.className = "dot ok";
    }
  } catch (err) {
    box.textContent = `agent state error: ${err.message}`;
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
    logAppend(el(`<div class="msg muted">▸ queued: ${esc(idea)}</div>`));
  } catch (err) {
    logAppend(el(`<div class="msg card"><strong class="dot bad">error</strong> ${esc(err.message)}</div>`));
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("job-start").onclick = startJob;
pollAgentState();
setInterval(pollAgentState, 4000);
connectStream();
