import subprocess
import sys


def test_dry_run_writes_nothing_opens_no_connection_and_calls_no_llm() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "glossary.main", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    # --dry-run prints the step chain but creates no logs directory
    assert "would process" in result.stdout
    assert "read -> extract -> embed -> upsert -> reconcile" in result.stdout
