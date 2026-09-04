#!/usr/bin/env bash
# PostToolUse hook: autofixes the edited .py file with ruff (check --fix +
# format). Never blocks the turn — but remaining non-autofixable violations
# are surfaced (exit 1: visible, non-blocking) instead of swallowed.
set -uo pipefail

[[ -n "${PY_HOOKS_DISABLE:-}" ]] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/hook_common.sh"
read_hook_target

[[ "$HOOK_FILE_PATH" == *.py ]] || exit 0
[[ -f "$HOOK_FILE_PATH" ]] || exit 0

cd "$HOOK_CWD" || exit 0

command -v uv >/dev/null 2>&1 || report_missing "ruff_autofix hook: 'uv' not found on PATH — skipped ruff for $HOOK_FILE_PATH"

if ! check_output="$(uv run ruff check --fix "$HOOK_FILE_PATH" 2>&1)"; then
  uv run ruff --version >/dev/null 2>&1 || report_missing "ruff_autofix hook: 'ruff' not available via 'uv run' — skipped for $HOOK_FILE_PATH"
  uv run ruff format "$HOOK_FILE_PATH" >/dev/null 2>&1
  printf '%s\n' "$check_output" >&2
  exit 1
fi

uv run ruff format "$HOOK_FILE_PATH" >/dev/null 2>&1
exit 0
