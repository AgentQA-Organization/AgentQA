# AgentQA Studio — stop-server button (design)

**Date:** 2026-07-27
**Status:** Approved
**Scope:** One new endpoint (`POST /api/shutdown`), one topbar button with a
confirm dialog, tests, and a docs line. No mailbox, protocol, or skill changes.

---

## Goal

Let the user stop the Studio daemon from the dashboard. Today the only way is
`Ctrl-C` in the terminal that launched it (`docs/agentqa-studio.md:118`), which
means finding that terminal again — awkward when Studio was launched with
`--open` and the user has been living in the browser ever since.

## What "stop" means here

**Stopping the server stops the browser bridge and nothing else.** Two things
survive a shutdown, and the UI has to say so rather than let the user assume
otherwise:

- **The attached agent.** The connector talks to the mailbox files under
  `.agentqa/studio/` directly (`skills/agentqa-studio/scripts/studio-wait.py`),
  never over HTTP. Killing the daemon does not stop a running `/agentqa-studio`
  turn; it keeps polling the inbox and bumping its heartbeat with nobody left to
  answer its questions.
- **An in-flight pytest run.** `RunManager` spawns `pytest` as a child process
  from a daemon thread (`studio/runner.py:47`). Shutdown orphans that child; the
  daemon thread that was reading its stdout dies with the interpreter.

Neither is cleaned up by this feature. The confirm dialog exists precisely so
the user chooses that outcome knowingly.

## Decisions (locked with the user)

1. **Warn, then allow.** The button is never disabled. If anything is in flight,
   the confirm dialog names it. Blocking was rejected: a dead agent can leave
   `state.json` stuck at `running`, which would strand the button forever.
2. **Server only.** No shutdown record is written to the mailbox and the daemon
   does not touch `state.json` — that would break the invariant in
   `studio/mailbox.py` ("Half A ... never writes the outbox", the agent owns
   state) and would force a Studio Protocol v1 extension across `protocol.py`,
   `protocol_v1.json`, `studio-wait.py`, and `SKILL.md`.
3. **Topbar power icon**, next to the theme toggle — visible from every tab,
   small enough not to invite an accidental click.

---

## Server: `POST /api/shutdown`

Respond `{"ok": true}` **first**, then stop the server from a separate daemon
thread:

```python
holder = {}            # filled in below, after the server is constructed
...
if u.path == "/api/shutdown":
    self._json({"ok": True})
    threading.Thread(target=holder["srv"].shutdown, daemon=True).start()
    return
...
srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
holder["srv"] = srv
return srv
```

Rationale for the ordering: `shutdown()` blocks until the `serve_forever` loop
exits, so calling it inline would race the response write. Writing the body
first guarantees the browser sees a clean 200 before the socket goes away.

`ThreadingHTTPServer` sets `daemon_threads = True`, so the two long-lived SSE
handlers (`studio/server.py:134`, `:148`) do not block `shutdown()` and do not
keep the process alive once `main()` returns.

`main()` gains `srv.server_close()` after `serve_forever()` returns, on both the
button path and the existing `KeyboardInterrupt` path, so the port is released
immediately instead of at interpreter exit. It also prints a final
`Studio stopped.` line so the terminal shows why it came back to the prompt.

**Rejected alternatives.** A `threading.Event` that `main()` waits on while
`serve_forever` runs in a side thread costs `make_server` its self-containment
(tests would have to build the wait loop themselves) for no behavioral gain.
`os._exit(0)` inside the handler cannot deliver the response and would kill the
pytest process in the test suite.

**Not in scope: request authentication.** The daemon binds `127.0.0.1` and every
existing endpoint is unauthenticated, including `POST /api/run`, which executes
pytest. Adding an `Origin` check to `/api/shutdown` alone would be inconsistent
and would not raise the actual security floor.

---

## Client: button, dialog, stopped overlay

### Button

`#stop-server`, reusing the existing `.icon-btn` class with a power-symbol SVG,
placed after `#theme-toggle` in the topbar. Hover state shifts to
`var(--danger)`; `title` and `aria-label` read "Stop the Studio server".

### Warning text — one pure function

```js
function shutdownWarnings(state, runActive) { … }   // → string[]
```

| Condition | Warning |
|---|---|
| `state.attached && state.status === "running"` | Agent is running a job. |
| `state.attached && state.status === "waiting"` | Agent is waiting on your answer — you won't be able to answer once Studio stops. |
| `runActive` | A pytest run is streaming — the test process will be left running. |

Pure and top-level so it can be sliced out of `app.js` and exercised through
node, the pattern `studio/tests/test_agent_badge.py` already establishes for
`attachView`.

On click, the handler fetches `/api/studio/state` fresh (rather than trusting
the 4-second poll's last value) and reads the module-level `activeRun`.

### Dialog

A `<dialog>` opened with `showModal()` — Esc-to-dismiss and focus trapping come
free — styled from the existing `.card` / `.btn` vocabulary.

```
Stop Studio server?
⚠ Agent is waiting on your answer — you won't be able to answer once Studio stops.
The agent in Claude Code keeps running; stop it there separately.
                                        [Cancel]  [Stop server]
```

- Warnings render as a list; with none, the body is just the agent note.
- **The agent note always shows**, warnings or not. It is the single most
  misreadable thing about this button.
- Confirm button uses `.btn-danger`; Cancel uses `.btn` and takes initial focus.

### After confirming

1. `POST /api/shutdown`.
2. Close both `EventSource` objects and `clearInterval` the agent-state poll.
   Without this the browser reconnects to a dead server forever and floods the
   console. `connectStream()` currently discards its `EventSource`
   (`studio/static/app.js:515`); it must keep a module-level reference so the
   stream can be closed.
3. Replace the page with a stopped overlay: "Studio stopped" plus
   "Run `agentqa-studio` to start it again."

A network error on the POST is treated as success — the connection dropping as
the server dies is the expected shape of this request, not a failure worth
reporting.

---

## Tests

**`studio/tests/test_server.py`** — the existing `live_server` fixture yields
only a base URL, so the shutdown test builds its own server and `serve_forever`
thread (mirroring the fixture) in order to assert on that thread:

- `POST /api/shutdown` returns 200 with `{"ok": true}`.
- The `serve_forever` thread joins within ~2s of the response.
- A request issued after that fails to connect.

**New `studio/tests/test_shutdown_warnings.py`** — same node-slicing harness as
`test_agent_badge.py`, over `shutdownWarnings`:

- attached + idle, no run → `[]`
- attached + `running` → job warning
- attached + `waiting` → answer warning
- `runActive = true` → pytest warning (and both warnings together when the agent
  is busy too)

---

## Docs

`docs/agentqa-studio.md:118` currently reads "`Ctrl-C` stops it." Update to
document the topbar power button as the primary way to stop Studio, with
`Ctrl-C` as the terminal equivalent, and state that neither stops an attached
agent.

## Files touched

| File | Change |
|---|---|
| `studio/server.py` | `POST /api/shutdown`, server holder, `server_close()` + final print in `main()` |
| `studio/static/index.html` | `#stop-server` button, `<dialog>` markup |
| `studio/static/app.js` | `shutdownWarnings()`, click/confirm handler, stream refs, stopped overlay |
| `studio/static/style.css` | Danger hover on `.icon-btn`, dialog + overlay styles |
| `studio/tests/test_server.py` | Shutdown endpoint tests |
| `studio/tests/test_shutdown_warnings.py` | New — warning-text tests via node |
| `docs/agentqa-studio.md` | How to stop Studio |

## Out of scope

- Killing the orphaned pytest child, or any process cleanup beyond the daemon.
- Any signal to the attached agent (mailbox, protocol, or skill changes).
- Restarting Studio from the browser.
- Authentication or CSRF protection on the new endpoint (see above).
