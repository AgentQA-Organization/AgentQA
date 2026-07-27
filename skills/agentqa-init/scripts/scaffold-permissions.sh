#!/usr/bin/env bash
# Allow AgentQA's own writes without a permission dialog, so a Studio run only
# raises a card for changes outside its working area. Idempotent; merges.
# Usage: scaffold-permissions.sh [--check]   (--check: validate only)
set -euo pipefail

ROOT="${AGENTQA_PROJECT_ROOT:-$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

python3 - "$ROOT" "$CHECK" <<'PY'
import json, re, sys
from pathlib import Path

root, check = Path(sys.argv[1]), sys.argv[2] == "1"

# test_dir is the one repo-specific piece; everything else is fixed.
test_dir = "AutomationTests"
cfg = root / ".agentqa" / "config.yml"
if cfg.is_file():
    m = re.search(r"^test_dir:\s*(\S+)", cfg.read_text(encoding="utf-8"), re.M)
    if m:
        test_dir = m.group(1).strip().strip("\"'")

# Edit(...) and not Write(...): Claude Code's file permission checks match only
# Edit(path) and Read(path) rules. Edit covers every file-editing tool; a
# Write(path) rule is accepted, warned about at startup, and never matched.
wanted = ["Edit(/.agentqa/**)", "Edit(/%s/**)" % test_dir.strip("/")]

path = root / ".claude" / "settings.json"
data = {}
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        print("settings.json is not valid JSON — fix it by hand", file=sys.stderr)
        sys.exit(1)

allow = list(((data.get("permissions") or {}).get("allow")) or [])
missing = [r for r in wanted if r not in allow]

if check:
    if missing:
        print("permission scaffold: missing %s" % ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    print("permission scaffold: OK")
    sys.exit(0)

allow.extend(missing)
data.setdefault("permissions", {})["allow"] = allow
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("permission scaffold: %d rule(s) added" % len(missing))
PY
