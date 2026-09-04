# Shared helpers for Claude Code hooks (PostToolUse and Stop). Sourced, not executed directly.

extract_json_string() {
  local key="$1" re
  re="\"${key}\"[[:space:]]*:[[:space:]]*\"([^\"]*)\""
  if [[ "$HOOK_PAYLOAD" =~ $re ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
}

extract_json_bool() {
  local key="$1" re
  re="\"${key}\"[[:space:]]*:[[:space:]]*(true|false)"
  if [[ "$HOOK_PAYLOAD" =~ $re ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
}

unescape_backslashes() {
  local s="$1"
  printf '%s' "${s//\\\\/\\}"
}

# Reads the hook's stdin JSON once and sets HOOK_FILE_PATH / HOOK_CWD /
# HOOK_STOP_HOOK_ACTIVE. HOOK_FILE_PATH is empty for hooks that don't carry
# tool_input (e.g. Stop) — callers that need it check for that themselves.
read_hook_target() {
  HOOK_PAYLOAD="$(cat)"
  HOOK_FILE_PATH="$(unescape_backslashes "$(extract_json_string file_path)")"
  HOOK_CWD="$(unescape_backslashes "$(extract_json_string cwd)")"
  HOOK_STOP_HOOK_ACTIVE="$(extract_json_bool stop_hook_active)"
}

# Reports a missing dependency without blocking the turn (exit 1: visible, non-blocking).
report_missing() {
  echo "$1" >&2
  exit 1
}
