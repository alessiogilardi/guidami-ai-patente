import os
import subprocess
import sys
from pathlib import Path


def test_dry_run_writes_nothing_opens_no_connection_and_calls_no_llm() -> None:
    logs_dir = Path("logs")
    before = set(logs_dir.glob("translate_glossary_terms_*")) if logs_dir.exists() else set()

    env = {
        **os.environ,
        "AGENTS_DIR": "configs/agents",
        "OPENROUTER_API_KEY": "test-key-not-a-real-credential",
    }
    result = subprocess.run(
        [sys.executable, "-m", "glossary.translate_main", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )

    after = set(logs_dir.glob("translate_glossary_terms_*")) if logs_dir.exists() else set()

    assert result.returncode == 0
    assert after == before
