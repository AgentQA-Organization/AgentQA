#!/usr/bin/env python3
"""Two-phase, dedup-enforced writer for .agentqa/memory/ notes. Stdlib only.

  memory-write.py propose --note <path|stem> --category <cat> --text "<obs>"
  memory-write.py apply --op ADD    --note <path|stem> --category <cat> --text "<obs>"
  memory-write.py apply --op UPDATE --target <file:line> --category <cat> --text "<obs>"
  memory-write.py apply --op DELETE --target <file:line>
  memory-write.py apply --op NOOP

`propose` prints the top-3 most-similar existing observations so the caller can
consciously choose ADD/UPDATE/DELETE/NOOP; writing is only possible via `apply`.
Similarity is textual, so it catches near-identical restatements and misses the
same fact worded differently — read the three lines, don't just take the score.

Reads and writes stay inside the persistent store (flows/, screens/, failures/,
env.md). The generated index and the two session dotfiles are refused: an edit to
the first is erased on the next rebuild, and an edit to the second would put a
claim nobody verified where later runs read it as fact.

UPDATE/DELETE require the memory store to be under git, so a wrong edit is one
`git checkout HEAD -- .agentqa/memory` away; they refuse only on unresolved merge
conflicts, which a revert would discard. Accumulated edits from the same session
are fine — one checkout undoes the whole batch. Paths resolve under --memory-dir
(.agentqa/memory).
"""
import argparse
import difflib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from memory_common import (  # noqa: E402
    CATEGORIES, IDENTIFIER_RE, ID_STATUSES, OBS_HEADER, MemoryPathError,
    iter_observations, resolve_persistent, secret_findings,
)


def _key(category, text):
    return f"[{category}] {text}"


def rank_similar(memory_dir, category, text, k=3):
    target = _key(category, text)
    scored = []
    for p, i, cat, txt in iter_observations(memory_dir):
        ratio = difflib.SequenceMatcher(None, target, _key(cat, txt)).ratio()
        scored.append((ratio, cat == category, p, i, cat, txt))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [(r, p, i, c, t) for (r, _s, p, i, c, t) in scored[:k]]


def resolve_note(memory_dir, note):
    return resolve_persistent(memory_dir, note)


def parse_target(memory_dir, target):
    if ":" not in target:
        raise ValueError(f"--target must be file:line, got {target!r}")
    file_part, line_part = target.rsplit(":", 1)
    return resolve_persistent(memory_dir, file_part), int(line_part)


def validate_observation(category, text):
    """Reasons this observation must not be written, as a list of strings.

    Both checks guard against damage that shows up much later: a mistyped
    category is a fact that quietly drops out of every query built on the
    schema, and a literal credential in a committed, team-shared store is in git
    history from the moment it lands.
    """
    problems = []
    if category not in CATEGORIES:
        problems.append(
            f"unknown category [{category}] — use one of: "
            + ", ".join(sorted(CATEGORIES))
        )
    if category == "identifier":
        m = IDENTIFIER_RE.match(text.strip())
        if not m:
            problems.append(
                "identifier observations must read "
                "`<name> → <file/symbol>; <status> <YYYY-MM-DD> #<flow>`"
            )
        elif m.group("status") not in ID_STATUSES:
            problems.append(
                f"unknown identifier status {m.group('status')!r} — use "
                + " or ".join(sorted(ID_STATUSES))
            )
    problems += [msg for sev, msg in secret_findings(text) if sev == "error"]
    return problems


def add_observation(note_path, category, text):
    if not note_path.exists():
        raise FileNotFoundError(
            f"{note_path} does not exist — create the note "
            f"(frontmatter: title/type/summary) before adding observations."
        )
    content = note_path.read_text(encoding="utf-8")
    line = f"- [{category}] {text}"
    if OBS_HEADER in content:
        new = content.rstrip("\n") + "\n" + line + "\n"
    else:
        new = content.rstrip("\n") + "\n\n" + OBS_HEADER + "\n" + line + "\n"
    note_path.write_text(new, encoding="utf-8")
    return line


def _read_lines(note_path):
    if not note_path.exists():
        raise FileNotFoundError(f"{note_path} does not exist")
    return note_path.read_text(encoding="utf-8").splitlines()


def update_line(note_path, lineno, category, text):
    lines = _read_lines(note_path)
    if not 1 <= lineno <= len(lines):
        raise IndexError(f"{note_path}:{lineno} out of range (1..{len(lines)})")
    lines[lineno - 1] = f"- [{category}] {text}"
    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def delete_line(note_path, lineno):
    lines = _read_lines(note_path)
    if not 1 <= lineno <= len(lines):
        raise IndexError(f"{note_path}:{lineno} out of range (1..{len(lines)})")
    del lines[lineno - 1]
    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def memory_status(memory_dir):
    """Porcelain status lines for the memory dir, or None if git can't say.

    The pathspec is resolved to an absolute path on purpose: `git status -- <rel>`
    is interpreted relative to cwd, and cwd here IS the memory dir, so a relative
    pathspec looks for `.agentqa/memory/.agentqa/memory`, matches nothing, and
    every dirty tree reads as clean.
    """
    memory_dir = Path(memory_dir).resolve()
    cwd = memory_dir if memory_dir.is_dir() else memory_dir.parent
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--", str(memory_dir)],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def memory_dir_dirty(memory_dir):
    """True=dirty, False=clean, None=unknown (not a git repo / git missing)."""
    lines = memory_status(memory_dir)
    return None if lines is None else bool(lines)


def unrevertable(memory_dir):
    """Status lines that a `git checkout HEAD -- <memory>` would NOT undo.

    Modified tracked files are fine — one checkout restores the whole batch at
    once, so refreshing eleven observations is exactly as recoverable as
    refreshing one. Merge conflicts are not: reverting them loses work that was
    never committed anywhere.
    """
    lines = memory_status(memory_dir)
    if not lines:
        return []
    return [ln for ln in lines if ln[:2].strip() in ("U", "UU", "AA", "DU", "UD")
            or "U" in ln[:2]]


REINDEX_HINT = ("→ run `python3 <skill>/scripts/memory-index.py {d}` "
                "(python3 scripts/memory-index.py) to refresh index.md")


def _rel(memory_dir, p):
    """Store-relative path — what `--target` expects back."""
    try:
        return str(Path(p).resolve().relative_to(Path(memory_dir).resolve()))
    except ValueError:
        return str(p)


def cmd_propose(args):
    try:
        resolve_persistent(args.memory_dir, args.note)
    except MemoryPathError as e:
        sys.exit(f"refusing propose: {e}")
    top = rank_similar(args.memory_dir, args.category, args.text)
    print(f"Top-{len(top)} similar in {args.memory_dir}:")
    if not top:
        print("  (none — the store has no observations yet)")
    for ratio, p, i, cat, txt in top:
        print(f"  [{ratio:.2f}] {_rel(args.memory_dir, p)}:{i}  [{cat}] {txt}")
    print("\n→ Decide, then re-run one of:")
    print(f'  apply --op ADD    --note {args.note} --category {args.category} --text "{args.text}"')
    print('  apply --op UPDATE --target <file:line> --category <cat> --text "..."')
    print("  apply --op DELETE --target <file:line>")
    print("  apply --op NOOP   (already covered — no write)")
    return 0


def _guard_clean(args, op):
    """Refuse only when the edit could not be undone.

    The point of this guard is that a wrong edit is one revert away — and a
    committed baseline gives you that for the whole session, however many
    observations you refresh. Demanding a pristine tree before *every* write
    made the common case impossible: Phase 3 refreshes every identifier it just
    verified, and the first UPDATE would block the rest.
    """
    if args.force:
        return
    blocked = unrevertable(args.memory_dir)
    if blocked:
        sys.exit(
            f"refusing {op}: {args.memory_dir} has unresolved merge conflicts, "
            f"which a revert would discard:\n  " + "\n  ".join(blocked)
            + "\nResolve and commit them first, or pass --force."
        )
    if memory_status(args.memory_dir) is None:
        # Not a git repo (or no git). Say so rather than refusing — plenty of
        # stores start life untracked, and blocking them would be a regression.
        print(
            f"warning: {args.memory_dir} is not under git, so this {op} cannot "
            f"be reverted automatically. Consider committing the memory store.",
            file=sys.stderr,
        )


def _guard_valid(args, op):
    problems = validate_observation(args.category, args.text)
    if problems:
        sys.exit(f"refusing {op}:\n  " + "\n  ".join(problems))


def cmd_apply(args):
    op = args.op
    if op == "NOOP":
        print("NOOP: no write.")
        return 0
    try:
        if op == "ADD":
            _guard_valid(args, op)
            note = resolve_persistent(args.memory_dir, args.note)
            line = add_observation(note, args.category, args.text)
            print(f"ADDED {_rel(args.memory_dir, note)}: {line}")
        elif op == "UPDATE":
            # Resolve the target before the git guard, so a refused path fails
            # on the path rather than on an unrelated warning about the tree.
            note, lineno = parse_target(args.memory_dir, args.target)
            _guard_valid(args, op)
            _guard_clean(args, op)
            update_line(note, lineno, args.category, args.text)
            print(f"UPDATED {_rel(args.memory_dir, note)}:{lineno}")
        elif op == "DELETE":
            note, lineno = parse_target(args.memory_dir, args.target)
            _guard_clean(args, op)
            delete_line(note, lineno)
            print(f"DELETED {_rel(args.memory_dir, note)}:{lineno}")
    except MemoryPathError as e:
        sys.exit(f"refusing {op}: {e}")
    except IndexError as e:
        # Line numbers shift as a batch deletes lines, so a target taken from an
        # earlier `propose` can go stale mid-session. Say so instead of dumping a
        # traceback at whoever is halfway through refreshing eleven identifiers.
        sys.exit(f"refusing {op}: {e}\nRe-run `propose` (or `memory-index.py "
                 f"--stale`) to get the current file:line.")
    print(REINDEX_HINT.format(d=args.memory_dir))
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Dedup-enforced writer for .agentqa/memory/.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("propose", help="show top-3 similar observations")
    pr.add_argument("--memory-dir", default=".agentqa/memory")
    pr.add_argument("--note", required=True)
    pr.add_argument("--category", required=True)
    pr.add_argument("--text", required=True)
    pr.set_defaults(func=cmd_propose)

    ap = sub.add_parser("apply", help="perform ADD/UPDATE/DELETE/NOOP")
    ap.add_argument("--memory-dir", default=".agentqa/memory")
    ap.add_argument("--op", required=True, choices=["ADD", "UPDATE", "DELETE", "NOOP"])
    ap.add_argument("--note")
    ap.add_argument("--category")
    ap.add_argument("--text")
    ap.add_argument("--target")
    ap.add_argument("--force", action="store_true")
    ap.set_defaults(func=cmd_apply)
    return p


def _validate(args, parser):
    if args.cmd == "apply":
        if args.op == "ADD" and not (args.note and args.category and args.text):
            parser.error("--op ADD requires --note, --category, --text")
        if args.op == "UPDATE" and not (args.target and args.category and args.text):
            parser.error("--op UPDATE requires --target, --category, --text")
        if args.op == "DELETE" and not args.target:
            parser.error("--op DELETE requires --target")


def _eval_log(argv):
    """Emit structured evidence only inside the deterministic eval harness."""
    state_dir = os.environ.get("AGENTQA_EVAL_STATE")
    if not state_dir:
        return
    target = Path(state_dir) / "calls.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.time(), "tool": "memory-write", "argv": list(argv)}
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    _eval_log(raw)
    parser = build_parser()
    args = parser.parse_args(raw)
    _validate(args, parser)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
