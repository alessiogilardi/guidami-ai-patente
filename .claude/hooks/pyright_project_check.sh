#!/usr/bin/env bash
# Stop hook: type-checks the whole project with pyright as a safety net for
# cross-file breakage that pyright_check.sh's per-file check can't see (e.g.
# a signature change breaking a caller in another file).
#
# Blocks the turn (exit 2) only if an error exists outside tests/ — same
# TDD red-phase exemption as pyright_check.sh, applied project-wide by
# classifying --outputjson diagnostics rather than a single file path.
#
# Skips itself when re-invoked after already blocking once this turn
# (stop_hook_active), so an error Claude can't resolve doesn't loop forever.
set -uo pipefail

[[ -n "${PY_HOOKS_DISABLE:-}" ]] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/hook_common.sh"
read_hook_target

[[ "$HOOK_STOP_HOOK_ACTIVE" == "true" ]] && exit 0

cd "$HOOK_CWD" || exit 0

command -v uv >/dev/null 2>&1 || report_missing "pyright_project_check hook: 'uv' not found on PATH — skipped"

if ! output="$(uv run pyright 2>&1)"; then
  uv run pyright --version >/dev/null 2>&1 || report_missing "pyright_project_check hook: 'pyright' not available via 'uv run' — skipped"
  printf '%s\n' "$output" >&2

  only_test_errors="$(uv run pyright --outputjson 2>/dev/null | uv run python -c '
import json, sys
diags = json.load(sys.stdin).get("generalDiagnostics", [])
errors = [d for d in diags if d.get("severity") == "error"]
outside_tests = [d for d in errors if "/tests/" not in d.get("file", "").replace("\\", "/")]
print("yes" if errors and not outside_tests else "no")
')"

  [[ "$only_test_errors" == "yes" ]] && exit 1
  exit 2
fi
exit 0
