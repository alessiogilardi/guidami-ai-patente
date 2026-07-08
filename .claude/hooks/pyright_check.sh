#!/usr/bin/env bash
# PostToolUse hook: type-checks the edited .py file with pyright. Type
# errors block the turn (exit 2) so Claude sees and fixes them immediately.
set -uo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/hook_common.sh"
read_hook_target

[[ "$HOOK_FILE_PATH" == *.py ]] || exit 0
[[ -f "$HOOK_FILE_PATH" ]] || exit 0

cd "$HOOK_CWD" || exit 0

command -v uv >/dev/null 2>&1 || report_missing "pyright_check hook: 'uv' not found on PATH — skipped pyright for $HOOK_FILE_PATH"
uv run pyright --version >/dev/null 2>&1 || report_missing "pyright_check hook: 'pyright' not available via 'uv run' — skipped for $HOOK_FILE_PATH"

if ! output="$(uv run pyright "$HOOK_FILE_PATH" 2>&1)"; then
  printf '%s\n' "$output" >&2
  exit 2
fi
exit 0
