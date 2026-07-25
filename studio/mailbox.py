"""Studio mailbox IO (daemon side): append inbox, read state, tail outbox.

Half A only ever bridges the browser to these files — it appends the browser's
messages to the inbox, tails the outbox to the browser, and reads state.json. It
never writes the outbox and never reads the outbox to act. The agent side owns the
outbox and state and touches these files directly, not through this module.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from studio import protocol


def studio_dir(repo_root: Path) -> Path:
    return Path(repo_root) / ".agentqa" / "studio"


def _append_line(path: Path, rec: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    # O_APPEND makes each write atomic against other appenders; a full-line write
    # means a reader never sees half a record.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def append_inbox(repo_root: Path, rec: Dict[str, Any]) -> Dict[str, Any]:
    protocol.validate(rec)
    _append_line(studio_dir(repo_root) / "inbox.jsonl", rec)
    return rec


def read_outbox(repo_root: Path) -> List[Dict[str, Any]]:
    path = studio_dir(repo_root) / "outbox.jsonl"
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    # Only consume newline-terminated (complete) lines; a partial trailing line
    # with no "\n" yet is left for a later read.
    complete = text.split("\n")[: text.count("\n")]
    for raw in complete:
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except ValueError:
                pass
    return out


def read_state(repo_root: Path) -> Dict[str, Any]:
    path = studio_dir(repo_root) / "state.json"
    if not path.is_file():
        return {"v": protocol.PROTOCOL_VERSION, "attached": False, "status": "idle",
                "current_job_id": None, "awaiting": None, "heartbeat_ts": None,
                "job_cursor": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"v": protocol.PROTOCOL_VERSION, "attached": False, "status": "idle"}


def tail_outbox(repo_root: Path, poll: float = 0.5) -> Iterator[Optional[Dict[str, Any]]]:
    """Yield outbox records oldest-first then follow appends; None on idle ticks.

    The SSE handler turns a record into a `data:` event and None into a `: ping`
    comment — the comment doubles as a disconnect probe so a closed browser stops
    the stream. The caller stops iterating on client disconnect.
    """
    path = studio_dir(repo_root) / "outbox.jsonl"
    seen = 0
    while True:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        complete = text.count("\n")
        if complete > seen:
            rows = text.split("\n")
            for raw in rows[seen:complete]:
                raw = raw.strip()
                if raw:
                    try:
                        yield json.loads(raw)
                    except ValueError:
                        pass
            seen = complete
        else:
            yield None
            time.sleep(poll)
