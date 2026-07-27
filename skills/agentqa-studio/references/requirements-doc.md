# An attached requirements document

Read this when a step-2 job record carries a `requirements` key. If it doesn't,
you never need this file.

```json
"requirements": {"name": "SRD-login.md", "path": ".agentqa/studio/uploads/ab12cd34-SRD-login.md", "chars": 4210}
```

## What it is

**One more `docs:` artifact, scoped to this job.** Read it at step 0, in the same
pass as the artifacts listed in `config.yml`'s `docs:`. Everything
`agentqa-write-test` already says about product artifacts applies unchanged — see
[`references/memory-model.md`](../../agentqa-write-test/references/memory-model.md)'s
Intent layer and [`references/clarify.md`](../../agentqa-write-test/references/clarify.md).

The file lives inside the gitignored mailbox and is **read-only** to you.

## The three rules that keep it honest

- **It pre-fills the clarify card, it never replaces it.** Where the document
  answers success / failure / blockers / entry point, pass that answer as the
  field's `default` so the user confirms-or-corrects instead of retyping. All four
  questions are still asked. A document never removes a question.

- **Trust order is unchanged: live hierarchy > memory > code > docs.** When the
  document and the live app disagree, the app wins — and say so, in a `progress`
  line and to the user. A stale spec is useful information.

- **Provenance.** Claims taken from it that you have not seen live go in
  `.session-requirement.md` under *From product docs (unverified)*, and die with
  the session. They never reach `flows/` or `screens/`.

## Announce it

Post a `progress` line naming the file, so the browser shows it was actually used:

```bash
python3 scripts/studio-post.py "$REPO" progress --stage map \
  --text 'Reading the attached requirements: SRD-login.md' --connector "$CONNECTOR"
```

If the path does not resolve, don't abort — say so in a `progress` line and run the
job as if no document were attached.
