# AgentQA Studio — permission bridge design

Route Claude Code's own permission dialogs to the Studio dashboard, so a tester
driving a test-writing run from the browser is never silently blocked by a prompt
that only exists in the terminal.

## The problem

Studio's M2 bridge routes *the agent's* questions to the browser: clarify, build,
review, and the system-view `ask`. It cannot route the questions the **harness**
asks. When Claude Code needs approval to run `Edit` on a Swift file, it raises a
terminal dialog and suspends the tool call. From the dashboard the run simply
stops: the last `progress` line sits there, the stepper does not move, and nothing
explains why.

This is not a bug in the mailbox. While the dialog is up the agent is not running
— the tool call has not returned — so it cannot post a card. No amount of work
inside `studio/` or the connector skill can observe the event.

Confirmed in both recorded Studio sessions on `test-auto-mytv`
(`73f6b2d9`, `1bf0f625`), each of which contains a real terminal rejection:

```
"The user doesn't want to proceed with this tool use. The tool use was rejected…"
```

The repo's `settings.local.json` allows `Bash(*)` but has no rule for file edits,
so every write AgentQA makes — `.session-requirement.md`, the generated test, the
accessibility-identifier edits — raises a dialog.

## The two halves

**Half 1 — don't ask about AgentQA's own working area.** Writes to `.agentqa/` and
the configured `test_dir` are the skill doing its job. They are covered by the
step-8 Review card, which shows the additions-only diff and the test files before
anything is committed. Prompting per file adds nothing.

**Half 2 — route what's left to the browser.** Edits to app source, and writes to
any path outside those two areas, become a card. App-source edits are gated
because they touch the product, not the test suite. Paths outside both areas are
gated because they are a signal the agent is doing something unintended, and that
is exactly the moment a human should see it.

## Mechanism — the `PermissionRequest` hook

Claude Code fires `PermissionRequest` **only when a permission dialog would appear**
(`PreToolUse`, by contrast, fires on every tool call). That self-filtering is what
makes the design small: the hook does not re-implement the allowlist, it reacts to
the harness having already decided a human is needed.

```
Agent calls Edit(HomeViewController.swift)
   │
   ├─ allowlist miss → dialog would appear
   │
   ├─ PermissionRequest hook (plugin-level, matcher = all tools)
   │     ├─ read <cwd>/.agentqa/studio/state.json
   │     │     not attached / missing / stale → print nothing, exit 0
   │     │                                       └─► terminal dialog, unchanged
   │     ├─ studio-post.py question --subtype permission
   │     ├─ studio-wait.py --reply-to <qid>     (≤540s)
   │     │     timeout / superseded → print nothing → terminal dialog
   │     └─ reply → {"decision": {"behavior": "allow"|"deny"}}
   │
   └─ Edit proceeds, or is blocked
```

### Why the matcher is every tool, not `Write|Edit`

`PermissionRequest` already means "you are about to be interrupted". Filtering by
tool name would drop precisely the unusual cases — an unexpected `Bash`, a
`WebFetch` — that a watching tester most needs to see. The tool name goes on the
card instead.

### Why there is no recursion

The hook runs `studio-post.py` and `studio-wait.py` as its own subprocesses. Hook
subprocesses are not agent tool calls and do not raise `PermissionRequest`. A
`PreToolUse` hook matching `Bash` would have bitten its own tail; this one cannot.

### Timeouts

Claude Code's hook timeout defaults to 600s and is configurable per hook. The hook
declares the default 600s and waits at most **540s** for a reply, so it returns a
decision of its own accord rather than being killed mid-wait — a killed hook leaves
the outcome to the harness's error handling, which is not a behaviour worth relying
on. The 60s margin covers the two script spawns either side of the wait.

540s is also the practical answer to "the tester walked away": after nine minutes
the prompt reappears in the terminal, where it would have been anyway.

### Every failure path ends at the terminal dialog

`PermissionRequest`'s `decision.behavior` accepts only `allow` and `deny` — there
is no `defer`. The fallback is therefore to emit **no decision at all**, which
leaves the default flow intact. No agent attached, daemon down, mailbox corrupt,
wait timed out, connector superseded: all print nothing and the tester gets the
terminal prompt exactly as today.

**No branch returns `allow` without a human click.** The hook can only ever remove
a prompt from the terminal by putting it in the browser, never by answering it.

## Protocol and card

A new question subtype, `permission`, reusing `kind: "review"`. `renderReview`
already provides everything the card needs and already tolerates the fields a
permission card omits:

| needed | `renderReview` provides |
|---|---|
| two one-click buttons | `Approve` / `Reject` |
| a reason when refusing | note field, revealed on `Reject` |
| a preview of the change | `rec.diff`, skipped when absent |

The whole UI change is one map entry. The code change is three lines:

```python
# studio/protocol.py
QUESTION_SUBTYPES = frozenset({"clarify", "ask", "build", "review", "permission"})
```
```js
// studio/static/app.js
const CARD_SUBTYPE_LABEL = { …, permission: "Permission" };
```
```python
# skills/agentqa-studio/scripts/studio-post.py
choices=["clarify", "ask", "build", "review", "permission"]
```

`test_every_protocol_subtype_has_a_label` (added with the `ask`-card label fix)
turns red if the protocol gains `permission` and the UI does not — the guard
written for the previous bug catches this one before it ships.

### Card contents

- `prompt` — the tool name and the path, e.g.
  *"Agent wants to edit app source: mytvb2c_swift/…/HomeViewController.swift"*
- `diff` — `old_string` → `new_string` for `Edit`; the head of `content` for
  `Write`; the command for `Bash`. Kept short: step-8 Review carries the full diff.

### Reply mapping — and how a rejection carries its reason

The two outcomes leave the hook by different doors, on purpose:

```python
if decision == "reject":
    sys.stderr.write(note or "Tester rejected this write from the Studio dashboard.")
    sys.exit(2)          # documented: PermissionRequest + exit 2 denies the permission
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {"behavior": "allow"}}}))
sys.exit(0)
```

Approve returns `{"behavior": "allow"}` as JSON. **Reject exits 2 with the note on
stderr**, rather than returning `{"behavior": "deny"}`, because the `decision`
object has no reason field — it carries `behavior`, `updatedInput`, and
`addPermissionRule` only, unlike `PreToolUse`'s `permissionDecisionReason`. For
hook events that can block, stderr is the documented channel for the blocking
reason, so exit 2 is how a rejection says *why*. Without it the agent receives a
bare "the user doesn't want to proceed" and has to ask the tester a question they
already answered.

**Spike this first.** The exit-code table states plainly that `PermissionRequest`
+ exit 2 denies the permission, so the denial itself is certain. What the table
does not state for this event specifically is whether stderr reaches the model —
it names `PostToolUse` and `PostToolUseFailure` as "shown to Claude" without
listing the blocking events. Task 1 of the implementation plan is a throwaway hook
that rejects with a recognisable sentinel string, run against a real session, to
observe whether that string appears in the agent's transcript. Everything else is
unaffected by the answer; only the fallback below depends on it.

**If stderr does not reach the model**, add a `studio-read.py --last-reply` and one
line in the connector SKILL.md: on a rejected tool call during a Studio run, read
the tester's note from the reply you were just given rather than asking again.
Build that only if the spike shows it is needed.

Independently of either, the hook posts the decision to the outbox as a `progress`
record. That is for the dashboard's own transcript — so the tester's decision and
reason are visible in the run history — **not** a delivery mechanism to the agent.
The outbox is the agent→browser direction; the agent never reads it.

### Deliberately out of scope for v1

`addPermissionRule` — an "allow for the rest of this session" button. It is
attractive and it is how permission fatigue gets solved, but it widens access in a
way that is hard to see afterwards. Add it when the card count proves annoying.

## Installation

**The hook ships with the plugin**: `hooks/hooks.json` at the plugin root, pointing
at `${CLAUDE_PLUGIN_ROOT}/studio/hooks/permission_bridge.py`. Installing the plugin
is enough; the state.json guard keeps it inert in repos that never run Studio, and
in terminal sessions where no agent is attached.

The script lives under `studio/` rather than in the connector skill because it is
infrastructure, not instructions: it runs with no agent in the loop and is
versioned with the protocol it speaks. It reaches the mailbox by invoking
`skills/agentqa-studio/scripts/studio-post.py` and `studio-wait.py` as
subprocesses — the same path the connector uses — so it shares their validation
rather than duplicating it. Both paths resolve from `${CLAUDE_PLUGIN_ROOT}`.

**The allowlist is per-repo**, written by `/agentqa-init init` into
`<repo>/.claude/settings.json`, because `test_dir` differs per project:

```json
{
  "permissions": {
    "allow": [
      "Edit(/.agentqa/**)",
      "Edit(/AutomationTests/**)"
    ]
  }
}
```

Three constraints behind those four lines:

- **`Edit(…)`, never `Write(…)`.** Claude Code's file permission checks match only
  `Edit(path)` and `Read(path)` rules. A `Write(path)` rule is accepted, warned
  about at startup, and never matched — a rule that looks correct and silently does
  nothing. `Edit` rules cover all file-editing tools.
- **Leading `/`, and project settings rather than local.** In `.claude/settings.json`
  a `/path` rule anchors at the repo root. In `settings.local.json` it anchors at
  the directory Claude Code was started from, so starting from a subdirectory
  would miss.
- **No `Read` rules.** Read-only tools are already permitted inside the working
  directory; adding rules would imply otherwise.

Init must **merge** into any existing file. `test-auto-mytv` already has an
`enabledPlugins` key in `settings.json` and an unrelated `settings.local.json`;
neither may be clobbered.

## Testing strategy

The hook's decision is extracted as a pure function over (state, reply) so it can
be tested without a browser, matching how `studio/tests/test_convo_render.py`
tests UI decisions and `test_studio_lifecycle.py` tests mailbox flows.

`studio/tests/test_permission_hook.py`:

| situation | hook emits |
|---|---|
| no agent attached | nothing → terminal dialog |
| `state.json` missing or malformed | nothing → terminal dialog |
| attached, tester clicks Approve | `{"behavior": "allow"}`, exit 0 |
| attached, tester clicks Reject | note on stderr, exit 2 |
| attached, Reject with an empty note | a default reason on stderr, exit 2 |
| no reply within 540s | nothing → terminal dialog |
| connector superseded mid-wait | nothing → terminal dialog |

Plus:

- an end-to-end pass through a real mailbox, in the style of
  `test_studio_lifecycle.py`: post → reply → hook returns `allow`
- `studio/tests/test_protocol.py`: `permission` is a valid subtype
- an `agentqa-init` test asserting **no generated permission rule uses the
  `Write(` form** — the failure mode is silent, so only a test catches it
- an `agentqa-init` test that scaffolding merges into an existing
  `settings.json` instead of replacing it

## Scope

In: the plugin hook and its script, the `permission` subtype, the card label, the
`studio-post.py` choice, the init allowlist scaffold, the tests above, and doc
updates to `docs/agentqa-studio.md` and the connector SKILL.md.

Out: `addPermissionRule`; routing permission prompts for sessions with no Studio
agent; any change to `agentqa-write-test`'s flow; the sandbox.

## Decisions locked

1. `PermissionRequest`, not `PreToolUse`.
2. Matcher is every tool.
3. Hook reaches the browser through the existing `studio-post.py` / `studio-wait.py`,
   not HTTP and not direct file writes — the mailbox stays the single source of truth.
4. Every failure path falls back to the terminal dialog; none auto-allows.
   Approve leaves as JSON on exit 0; reject leaves as exit 2 with the reason on
   stderr, which is the only channel `PermissionRequest` offers for a reason.
5. Auto-allowed: `.agentqa/**` and `<test_dir>/**`. Gated: app source and
   everything else.
6. Hook ships in the plugin; allowlist is scaffolded per repo by `/agentqa-init init`.
