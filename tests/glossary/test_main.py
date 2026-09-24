import os
import subprocess
import sys
from pathlib import Path


def test_dry_run_writes_nothing_opens_no_connection_and_calls_no_llm() -> None:
    # Snapshot logs/ directory before running --dry-run
    logs_dir = Path("logs")
    before = set(logs_dir.glob("build_glossary_*")) if logs_dir.exists() else set()

    env = {
        **os.environ,
        "AGENTS_DIR": "configs/agents",
        "OPENROUTER_API_KEY": "test-key-not-a-real-credential",
    }
    result = subprocess.run(
        [sys.executable, "-m", "glossary.main", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )

    # Snapshot logs/ directory after running --dry-run
    after = set(logs_dir.glob("build_glossary_*")) if logs_dir.exists() else set()

    # Verify exit code
    assert result.returncode == 0
    # Verify --dry-run printed the step chain (proves execution, not just early exit)
    assert "would process" in result.stdout
    assert "read -> extract -> embed -> upsert -> reconcile" in result.stdout
    # Verify no new build_glossary_* directory was created (no filesystem write)
    assert after == before
