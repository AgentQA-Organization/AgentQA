#!/usr/bin/env bash
# Mechanical wrapper for live exploration and behavioral-memory writes.
set -euo pipefail

SKILL_BASE="$(cd "$(dirname "$0")/.." && pwd)"
INIT_BASE="${AGENTQA_INIT_BASE:-$(cd "$SKILL_BASE/../agentqa-init" 2>/dev/null && pwd || true)}"

config_get() {
  local key="$1"
  [[ -f .agentqa/config.yml ]] || return 0
  sed -n "s/^${key}:[[:space:]]*\([^#]*\).*/\1/p" .agentqa/config.yml \
    | head -1 | tr -d ' "'
}

die() {
  echo "FAIL: $*" >&2
  exit 1
}

cmd="${1:-help}"
[[ $# -gt 0 ]] && shift

case "$cmd" in
  explore)
    app_id=""
    reset_policy=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --app-id) [[ $# -ge 2 ]] || die "--app-id requires a value"; app_id="$2"; shift 2 ;;
        --reset-policy) [[ $# -ge 2 ]] || die "--reset-policy requires a value"; reset_policy="$2"; shift 2 ;;
        *) die "unknown explore option: $1" ;;
      esac
    done
    [[ -n "$app_id" ]] || die "explore requires --app-id"

    reset_policy="${reset_policy:-$(config_get reset_app_data)}"
    reset_policy="${reset_policy:-always}"
    [[ "$reset_policy" == "always" || "$reset_policy" == "never" ]] \
      || die "reset_app_data must be always or never (got: $reset_policy)"

    if [[ "$reset_policy" == "always" ]]; then
      [[ -n "$INIT_BASE" && -f "$INIT_BASE/scripts/reset-app-data.sh" ]] \
        || die "agentqa-init reset script not found at $SKILL_BASE/../agentqa-init/scripts/reset-app-data.sh"
      "$INIT_BASE/scripts/reset-app-data.sh" "$app_id"
      echo "Data reset: done"
    else
      echo "Data reset: skipped (reset_app_data=never)"
    fi

    platform="$(config_get platform)"
    platform="${platform:-ios}"
    platform_args=()
    [[ "$platform" == "android" ]] && platform_args=(--platform android)
    [[ "$platform" == "ios" || "$platform" == "android" ]] \
      || die "platform must be ios or android (got: $platform)"
    agent-device open "$app_id" ${platform_args[@]+"${platform_args[@]}"}
    echo "Drive only with agent-device snapshot/press/fill until entry, success, and failure are observed."
    ;;

  note-propose)
    memory_dir=""
    file=""
    category=""
    observation=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --memory-dir) [[ $# -ge 2 ]] || die "--memory-dir requires a value"; memory_dir="$2"; shift 2 ;;
        --file) [[ $# -ge 2 ]] || die "--file requires a value"; file="$2"; shift 2 ;;
        --cat) [[ $# -ge 2 ]] || die "--cat requires a value"; category="$2"; shift 2 ;;
        --text) [[ $# -ge 2 ]] || die "--text requires a value"; observation="$2"; shift 2 ;;
        *) die "unknown note-propose option: $1" ;;
      esac
    done
    [[ -n "$memory_dir" && -n "$file" && -n "$category" && -n "$observation" ]] \
      || die "note-propose requires --memory-dir --file --cat --text"
    python3 "$SKILL_BASE/scripts/memory-write.py" propose \
      --memory-dir "$memory_dir" --note "$file" --category "$category" --text "$observation"
    echo "Inspect the proposal, then call note-apply with ADD, UPDATE, DELETE, or NOOP."
    ;;

  note-apply)
    op=""
    memory_dir=""
    file=""
    target=""
    category=""
    observation=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --op) [[ $# -ge 2 ]] || die "--op requires a value"; op="$2"; shift 2 ;;
        --memory-dir) [[ $# -ge 2 ]] || die "--memory-dir requires a value"; memory_dir="$2"; shift 2 ;;
        --file) [[ $# -ge 2 ]] || die "--file requires a value"; file="$2"; shift 2 ;;
        --target) [[ $# -ge 2 ]] || die "--target requires a value"; target="$2"; shift 2 ;;
        --cat) [[ $# -ge 2 ]] || die "--cat requires a value"; category="$2"; shift 2 ;;
        --text) [[ $# -ge 2 ]] || die "--text requires a value"; observation="$2"; shift 2 ;;
        *) die "unknown note-apply option: $1" ;;
      esac
    done
    [[ -n "$memory_dir" && -n "$op" ]] || die "note-apply requires --memory-dir and --op"
    case "$op" in
      ADD)
        [[ -n "$file" && -n "$category" && -n "$observation" ]] \
          || die "ADD requires --file --cat --text"
        python3 "$SKILL_BASE/scripts/memory-write.py" apply \
          --memory-dir "$memory_dir" --op ADD --note "$file" \
          --category "$category" --text "$observation"
        ;;
      UPDATE)
        [[ -n "$target" && -n "$category" && -n "$observation" ]] \
          || die "UPDATE requires --target --cat --text"
        python3 "$SKILL_BASE/scripts/memory-write.py" apply \
          --memory-dir "$memory_dir" --op UPDATE --target "$target" \
          --category "$category" --text "$observation"
        ;;
      DELETE)
        [[ -n "$target" ]] || die "DELETE requires --target"
        python3 "$SKILL_BASE/scripts/memory-write.py" apply \
          --memory-dir "$memory_dir" --op DELETE --target "$target"
        ;;
      NOOP)
        python3 "$SKILL_BASE/scripts/memory-write.py" apply \
          --memory-dir "$memory_dir" --op NOOP
        ;;
      *) die "--op must be ADD, UPDATE, DELETE, or NOOP" ;;
    esac
    ;;

  lint)
    memory_dir=".agentqa/memory"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --memory-dir) [[ $# -ge 2 ]] || die "--memory-dir requires a value"; memory_dir="$2"; shift 2 ;;
        *) die "unknown lint option: $1" ;;
      esac
    done
    python3 "$SKILL_BASE/scripts/memory-index.py" "$memory_dir"
    python3 "$SKILL_BASE/scripts/memory-lint.py" "$memory_dir"
    ;;

  *)
    echo "Usage: phase2-wrapper.sh explore|note-propose|note-apply|lint [options]" >&2
    exit 1
    ;;
esac
