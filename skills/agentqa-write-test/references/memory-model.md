# agentqa memory model — behavioral knowledge store

**This file is the schema.** Everything else — the SKILL.md steps, the store's own
`README.md`, the project README, and the docs pages (`docs/memory.md`) — points
here rather than restating it, so there is exactly one place to change when the
schema moves. Read this before touching memory; don't re-derive it.

Memory persists **behavioral** knowledge the skill hand-earns at runtime — real
navigation paths, native-vs-web screens, verified identifier placements,
phantom-failure signatures, build gotchas. It is NOT code knowledge (CodeGraph
regenerates that). Creed: *code reading lies; only the live hierarchy is truth* —
`agent-device snapshot` while exploring, Appium `page_source` once Appium is in
play (step 6 onward).

The schema is **platform-neutral** — it holds for iOS and Android alike. An
`[identifier]` records a logical name and where it's set; the *mechanism* behind
it (iOS `accessibilityIdentifier`, Android `contentDescription`/`resource-id`) is
the write step's concern, not the note's. When you record a screen's identifiers
or quirks, they read the same way whichever platform produced them.

## Where & format

- Lives in `.agentqa/memory/` at the host repo root, **committed** (team-shared).
- **No secrets** — credential env-var *names* only, never values. `memory-lint.py`
  and `memory-write.py` both refuse text that looks like a credential value.
- Notes are plain markdown: frontmatter plus **observations**, one fact per line:
  `- [category] fact #flow`. That's the whole format. There is no relation syntax
  and no link graph — the `#flow` tag is what ties a screen or a failure to the
  flows it belongs to, and it is what scoped Recall filters on.
- **`index.md` is generated, never committed.** It is a derived view of the notes,
  rebuilt from them in milliseconds, so committing it only buys merge conflicts on
  a file nobody edits. It is gitignored by the scaffold; Recall rebuilds it.

## Note types

| Folder / file | One note per | Captures |
|---|---|---|
| `flows/` | user flow | nav path, **the assertion that matters**, edge cases, native-vs-web per step |
| `screens/` | screen | native-or-web, identifier map (name → placement + verification status/date), quirks |
| `failures/` | phantom/flaky signature | symptom → cause → remedy (cross-flow library) |
| `env.md` | (single file) | build-policy rationale, credential env-var names, device/simulator + CodeGraph gotchas |

Those four are the **persistent store**, and they are the only paths
`memory-write.py` will write to. Anything else under `.agentqa/memory/` is either
generated (`index.md`) or session state (the dotfiles below), and a write landing
there would either be erased on the next rebuild or leak session-scoped claims
into the store later runs trust.

## Schema

- Frontmatter: `title`, `type` (`flow|screen|failure|env`), `tags`,
  `summary` (one line — the index is assembled from this), optional `last_verified`.
- Observation categories: `[flow-step]` `[assertion]` `[native]` `[web]`
  `[identifier]` `[quirk]` `[edge-case]` `[symptom]` `[cause]` `[remedy]`
  `[gotcha]` `[credential-env]`. The writer rejects anything else — a typo'd
  category is a fact that silently drops out of every later query.
- **Tag every observation with its flow** (`#login`, `#checkout`). This is the
  only thing connecting a screen note to the flows that traverse it, so an
  untagged observation is invisible to `--flow` recall even though it's in the
  store. A screen used by three flows carries all three tags.
- Identifier observation (encodes status + date):
  `- [identifier] <logical_name> → <file/symbol>; <status> <YYYY-MM-DD> #<flow>`
  status ∈ {`added-unverified`, `verified-in-hierarchy`}. There is no third
  status: staleness is *computed* from the date, not declared, so it can never
  disagree with the calendar.

## Lifecycle — four verbs

- **Recall** (read-on-start): rebuild the index, then load only what this flow
  needs — see *Scoped recall* below.
- **Verify-on-read**: recalled facts are *claims*, re-checked against the live
  hierarchy; stale claims are flagged, never blindly trusted.
- **Capture** (write-on-finish): append **deduped** observations via
  `scripts/memory-write.py` (`propose` shows the top-3 similar, then
  `apply --op ADD|UPDATE|DELETE|NOOP`). `propose` ranks by string similarity, so
  treat it as a prompt to look rather than a guarantee: it reliably catches
  near-identical restatements and will miss the same fact worded differently.
  `UPDATE` is the **Refresh** verb below; it and `DELETE` want the store under git
  so a wrong call is one `git checkout HEAD -- .agentqa/memory` away. That undoes
  the whole session's writes in one command, so refreshing eleven observations is
  as recoverable as refreshing one — they refuse only on unresolved merge
  conflicts, which a revert would silently discard.
- **Refresh**: a mismatch **updates** the observation and bumps its date rather
  than appending a contradiction.

**Memory trust = verify-delta:** on a repeat run, use the note as a map, confirm
known waypoints against live state, deep-dive only where reality diverges.

## Scoped recall

The store grows without bound; a run only needs the slice touching its flow.

```bash
python3 scripts/memory-index.py .agentqa/memory                  # rebuild index.md
python3 scripts/memory-index.py .agentqa/memory --flow <flow>    # this flow's slice
python3 scripts/memory-index.py .agentqa/memory --stale          # what needs re-verifying
```

`--flow` prints the matching flow notes, every screen note tagged `#<flow>`, and
the whole `failures/` headline list — failures stay unscoped on purpose, because a
phantom signature earned on checkout is exactly what you want when login times out
the same way. Nothing matches? That's a new flow, not an error; explore from
scratch.

`--stale` lists verified identifiers whose verification has aged past 30 days
(`--days N` to change it), each with the `file:line` to pass straight to
`memory-write.py --op UPDATE`. Age is a prompt to re-verify during exploration,
not a reason to delete: the identifier is probably still there, but nobody has
looked lately, and step 3 is walking those screens anyway.

## Validation

```bash
python3 scripts/memory-lint.py .agentqa/memory
```

Checks what silently corrupts a store: missing or malformed frontmatter (a note
with no `summary:` produces a blank index line and effectively disappears),
unknown observation categories, identifier lines that don't parse into
name/placement/status/date, notes filed outside the four persistent locations,
and text that looks like a committed credential. Errors exit non-zero; warnings
report and pass (`--strict` promotes them). Run it after a Capture batch and in
CI — the failure mode it prevents is a store that looks fine and answers nothing.

## Working layer — two ephemeral files

The `agentqa-write-test` skill maintains exactly two ephemeral files, both for the
current session only (deliberately not a `sessions/<run-id>/` tree). Both are
gitignored, never committed, invisible to `index.md`, `memory-write.py`, and
`memory-lint.py`, and **deleted at step 9** — or whenever the session ends
unfinished. They are session state, not knowledge: what deserves to persist is
captured into `flows/`, `screens/`, and `failures/`.

| File | Written | Holds |
|---|---|---|
| `.agentqa/memory/.session-requirement.md` | step 2 (clarify) | what the user asked for: request, **success**, **failure**, **blockers**, environment/preconditions — the contract steps 3–8 check themselves against |
| `.agentqa/memory/.run-checkpoint.md` | step 5 (build pause) | in-flight run state so step 6 resumes after a context break instead of re-clarifying and re-exploring |

- Requirement note frontmatter: `title`, `type: session-requirement`, `updated`.
  Sections: `## Request`, `## Success`, `## Failure`, `## Blockers`,
  `## Environment / preconditions` (template in
  [clarify.md](clarify.md)).
- Checkpoint frontmatter: `run_id`, `current_step`, `feature`, `updated`. Sections:
  `## Added identifiers (awaiting build+verify)`, `## Hypothesis under test`,
  `## Blocker` (e.g. `WAITING_FOR_HUMAN_BUILD`).

## Intent layer — product artifacts (optional, read-only)

Some teams already have SRDs, PM scenarios, user-flow docs, acceptance criteria.
When `docs:` is set in `.agentqa/config.yml` (local paths/globs), those files are
readable at step 0 and feed the clarify round. Many repos have none — the block is
absent by default and everything below simply doesn't apply.

**They are intent, not truth.** A spec says what the app was *meant* to do. It can
be stale, aspirational, or describe something that shipped differently — which puts
it *further* from reality than the source code, and the creed already says code
reading lies. So artifacts get the weakest trust of any source here: they are good
at the one thing neither code nor the live app can supply (what *should* count as
passing), and unreliable at everything the live hierarchy answers directly.

What they're for:
- **Pre-filling the clarify round.** Success / failure / blockers / entry point are
  the questions asked every run because only a human could answer them. A spec is a
  written answer — so propose it back for confirmation instead of asking cold. The
  user still decides; a doc never silently becomes the requirement.
- **Aiming exploration.** A described flow is another map for the step-3
  verify-delta pass — one more prior to confirm against live state, exactly like a
  recalled memory note.

**Provenance rule — spec claims stay session-scoped until observed live.**
Anything read from an artifact and not yet seen in the live hierarchy lives only in
`.agentqa/memory/.session-requirement.md`, which is deleted when the session ends.
It is never written into `flows/`, `screens/`, or `failures/`. Those hold what the
skill *observed*; letting an unverified doc claim in would poison the store that
later runs trust as a map, and it would be indistinguishable from a fact earned by
driving the app. (`memory-write.py` enforces the mechanical half of this: it can't
write to the ephemeral files, and it can't be pointed at one as an update target.)
Once exploration confirms a claim, it gets captured the normal way — as an
observation grounded in what you saw, not a quotation from the doc.

When a doc and the live app disagree, the live app wins and **the divergence is
worth surfacing** — a spec that no longer matches the build is useful information
for the user, not just noise to discard.

The skill **never writes to these files.** They are owned by whoever wrote them.

## Source-of-truth split (no duplication)

- `.agentqa/config.yml` — structured facts. `.agentqa/memory/` — narrative
  behavioral knowledge the skill earned and owns. `CLAUDE.md`/`AGENTS.md` — a
  pointer to `.agentqa/memory/`. `docs:` artifacts — external **intent**,
  read-only, owned by PM/BO/dev; read for requirements, never written, never
  authoritative over the live hierarchy.
- Trust order when they disagree: **live hierarchy > memory > code > docs.**
