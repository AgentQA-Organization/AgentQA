"""Requirements documents uploaded from the dashboard. Validation + storage, no IO policy.

A requirements doc is an **intent** artifact — the same kind `docs:` points at in
`.agentqa/config.yml` — handed to one job from the browser instead of committed
to the repo. It lands in the mailbox (`.agentqa/studio/uploads/`), which is
already gitignored, so uploading never dirties the user's tree.

Text formats only, on purpose. Word and PDF would have to be parsed to be useful
and this package has no dependencies to parse them with; a best-effort
extraction that silently drops a table is worse than a refusal that says how to
export the file properly.
"""
import re
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

MAX_CHARS = 200_000          # ~200 KB of text; a requirements doc is far under it
TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
# Formats people actually try to upload, each worth naming in the refusal.
RICH_SUFFIXES = frozenset({".doc", ".docx", ".pdf", ".rtf", ".pages", ".odt"})

EXPORT_HINT = (
    "Only Markdown or plain text can be read (.md, .markdown, .txt). "
    "Export it first — in Word: File → Save As → choose Plain Text, or paste "
    "the content into a .md file — then upload that. Markdown is preferred: "
    "its headings survive, so the agent can tell your success criteria from "
    "your blockers."
)


def uploads_dir(repo_root: Path) -> Path:
    return Path(repo_root) / ".agentqa" / "studio" / "uploads"


def suffix_of(filename: str) -> str:
    return Path(str(filename or "")).suffix.lower()


def check_document(filename: str, content: str) -> Optional[str]:
    """Return why this upload is refused, or None if it is acceptable."""
    if not str(filename or "").strip():
        return "A filename is required."
    suffix = suffix_of(filename)
    if suffix in RICH_SUFFIXES:
        return "%s files can't be read. %s" % (suffix, EXPORT_HINT)
    if suffix not in TEXT_SUFFIXES:
        return "%s is not a supported requirements file. %s" % (
            suffix or "That file", EXPORT_HINT)
    if not isinstance(content, str) or not content.strip():
        return "The document is empty — there is nothing to use as requirements."
    if len(content) > MAX_CHARS:
        return ("The document is too large (%d characters, limit %d). Upload just "
                "the sections describing this flow." % (len(content), MAX_CHARS))
    return None


def safe_name(filename: str) -> str:
    """A storage name derived from an untrusted one.

    The filename arrives from a browser, so it decides nothing about *where* the
    file goes: only the basename is considered, every character outside a small
    allowlist is folded to `-`, and a stem that survives as nothing still gets a
    usable name.
    """
    base = Path(str(filename or "")).name
    stem = Path(base).stem
    suffix = suffix_of(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    if not stem:
        stem = "requirements"
    if suffix not in TEXT_SUFFIXES:
        suffix = ".md"
    return (stem[:60] + suffix)


def store(repo_root: Path, filename: str, content: str) -> Dict[str, Any]:
    """Write an already-validated document; return its record for the job.

    `path` is repo-relative so it can travel in a mailbox record and be opened
    by an agent that only knows the repo root.
    """
    d = uploads_dir(repo_root)
    d.mkdir(parents=True, exist_ok=True)
    name = "%s-%s" % (uuid.uuid4().hex[:8], safe_name(filename))
    (d / name).write_text(content, encoding="utf-8")
    return {
        "name": Path(str(filename)).name,      # what the user called it
        "path": ".agentqa/studio/uploads/%s" % name,
        "chars": len(content),
    }


def prune(repo_root: Path, keep_paths) -> int:
    """Delete stored uploads that no surviving job refers to; return the count.

    Attach archives the mailbox but must not archive an upload a carried-forward
    job still points at — so uploads are pruned by reachability instead.
    """
    d = uploads_dir(repo_root)
    if not d.is_dir():
        return 0
    keep = {Path(str(p)).name for p in keep_paths if p}
    removed = 0
    for f in d.iterdir():
        if f.is_file() and f.name not in keep:
            f.unlink()
            removed += 1
    return removed
