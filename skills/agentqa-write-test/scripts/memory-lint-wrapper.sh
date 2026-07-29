#!/usr/bin/env bash
set -euo pipefail

SKILL_BASE="$(cd "$(dirname "$0")/.." && pwd)"
MEMORY_DIR="${1:-.agentqa/memory}"

[[ $# -le 1 ]] || { echo "Usage: memory-lint-wrapper.sh [memory-dir]" >&2; exit 1; }
python3 "$SKILL_BASE/scripts/memory-index.py" "$MEMORY_DIR"
python3 "$SKILL_BASE/scripts/memory-lint.py" "$MEMORY_DIR"
echo "Memory lint: PASS"
