"""Tests for cli/logging_setup.py."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_root_handlers() -> Iterator[None]:
    """Isolates each test from the global root-logger state `configure_logging` mutates.

    Closes any handler added during the test (e.g. a `FileHandler`) before restoring the
    original handler list, so the underlying log file is not left open -- an open handle
    would block pytest's `tmp_path` cleanup on Windows.
    """
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    for handler in root.handlers:
        if handler not in original_handlers:
            handler.close()
    root.handlers[:] = original_handlers
    root.setLevel(original_level)


def test_configure_logging_dry_run_creates_no_directory_and_returns_none(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    log_file = configure_logging(tmp_path, "prepare", dry_run=True)

    assert log_file is None
    assert not (tmp_path / "logs").exists()


def test_configure_logging_creates_run_dir_and_log_file(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    log_file = configure_logging(tmp_path, "status", dry_run=False)

    assert log_file is not None
    assert log_file.name == "run.log"
    assert log_file.parent.parent == tmp_path / "logs"
    assert log_file.parent.name.startswith("ingest_status_")
    assert log_file.exists()


def test_configure_logging_avoids_same_minute_collision_with_numeric_suffix(
    tmp_path: Path,
) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    first = configure_logging(tmp_path, "reset", dry_run=False)
    second = configure_logging(tmp_path, "reset", dry_run=False)

    assert first is not None
    assert second is not None
    assert second.parent.name == f"{first.parent.name}_2"
