# AgentQA Studio — attaching requirements, and a guide for writing them

**Date:** 2026-07-27
**Status:** implemented

Two additions to the Agent panel: a requirements document can be attached to a
job, and a button explains how to write one. Both exist because the Clarify card
is where a run goes wrong — a tester who has a spec has been retyping it into
three text fields, and a tester who has no spec has been guessing what the agent
needs.

## The key decision: this is not a new concept

`agentqa-write-test` already has a slot for exactly this. `.agentqa/config.yml`
takes a `docs:` block pointing at SRDs, PM scenarios and acceptance criteria, and
the skill's **Intent layer** defines their treatment precisely: read at step 0,
used to pre-fill the clarify round, never authoritative, session-scoped
provenance, trust order `live hierarchy > memory > code > docs`.

An uploaded file is the same artifact delivered per job instead of per repo, so
it goes in that slot rather than beside it. Nothing about the write-test flow
changes; the connector just tells it there is one more artifact to read. Had the
upload become its own concept, every rule above would have needed restating —
and the one that matters most (a document is *intent*, and the live app
overrules it) is the easiest to lose.

## Storage and transport

Uploaded text is written to `.agentqa/studio/uploads/<uuid8>-<safe-name>`, inside
the mailbox, which already carries a `.gitignore` of `*`. Attaching a file
therefore never dirties the user's tree, and the daemon never writes outside the
one directory it owns.

The `job` record carries a pointer, not the text:

```json
{"type": "job", "flow_idea": "…", "requirements": {"name": "SRD-login.md", "path": ".agentqa/studio/uploads/ab12cd34-SRD-login.md", "chars": 4210}}
```

`inbox.jsonl` is read whole on every poll of `studio-wait.py`, so inlining a
multi-thousand-character spec would tax every poll for the life of the session.
`validate()` accepts the field only as `{name, path}`+ — additive to Protocol v1,
so an older connector ignores it and still runs the job.

**Uploads are not archived on attach.** A queued job carries forward, and a
carried job pointing at an archived file would be worse than no job at all. They
are pruned by reachability instead: anything the new inbox does not reference
belonged to the session that was just replaced.

## Text only, and why the refusal is long

`.doc`, `.docx`, `.pdf`, `.rtf`, `.pages`, `.odt` are refused. This package has
no dependencies and adding a document parser to it would buy a best-effort
extraction that can silently drop a table — and a requirement that quietly went
missing is worse than one that was never accepted. The refusal therefore carries
the fix (`File → Save As → Plain Text`, or paste into a `.md`) and the reason to
prefer Markdown: headings survive, so the agent can tell a success criterion
from a blocker.

Validation lives in `studio/uploads.py` as pure functions (`check_document`,
`safe_name`) so the same answer reaches the browser and a direct POST. The
filename is untrusted input for a path: only its basename is considered, every
character outside `[A-Za-z0-9._-]` is folded to `-`, and a uuid prefix makes
collisions impossible. `../../../../etc/passwd.md` lands in the uploads
directory like everything else.

## The job still needs a name

Attaching a spec and pressing Start with an empty idea box is the obvious way to
use this, so `deriveIdea()` names the job from the document's first heading, then
the filename, then nothing. An empty box and no file still queues nothing.

## The guide

A modal in the Agent panel — the pattern the stop dialog already established, so
reading it costs no context. Its content is drawn from
`agentqa-write-test/references/clarify.md` rather than invented: the four
questions asked every run, the "never ask these" list inverted into *skip it, the
agent finds this itself*, and the note that a document is intent the agent will
still confirm.

The template is a single node in `index.html`; the dialog, the copy button and
the download all read that same node, so the three cannot drift. It mirrors the
shape of `.session-requirement.md`, which is what the answers become.

## Testing

- `studio/tests/test_uploads.py` — 16 tests: accepted formats, every refusal
  path with its message, collisions, traversal, odd filenames, the gitignore.
- `studio/tests/test_convo_render.py` — `deriveIdea` under node.
- `skills/agentqa-studio/tests/test_studio_lifecycle.py` — an upload a carried
  job needs survives attach; a cancelled job's upload is pruned.
- Verified end-to-end in headless Chrome over CDP, driving the real
  `<input type=file>` via `DOM.setFileInputFiles`: a `.docx` is refused with the
  export hint, the `.md` attaches, Start with an empty box produces the job
  `"Sign in with a valid account"` from the document's `# ` heading, and the
  written `inbox.jsonl` record points at a readable stored file.
