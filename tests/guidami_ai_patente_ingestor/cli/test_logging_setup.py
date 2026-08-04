"""Tests for cli/logging_setup.py."""

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_litellm_log_env() -> Iterator[None]:
    """Isolates each test from the `LITELLM_LOG` env var `configure_logging` sets."""
    original = os.environ.get("LITELLM_LOG")
    yield
    if original is None:
        os.environ.pop("LITELLM_LOG", None)
    else:
        os.environ["LITELLM_LOG"] = original


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


def test_no_stream_handler_when_console_handler_disabled(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    configure_logging(tmp_path, "prepare", dry_run=False, use_console_handler=False)

    root = logging.getLogger()
    stream_handlers = [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert stream_handlers == []
    assert len(file_handlers) == 1


def test_configure_logging_defaults_litellm_log_to_warning(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    os.environ.pop("LITELLM_LOG", None)

    configure_logging(tmp_path, "prepare", dry_run=True)

    assert os.environ["LITELLM_LOG"] == "WARNING"


def test_configure_logging_does_not_override_existing_litellm_log(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    os.environ["LITELLM_LOG"] = "DEBUG"

    configure_logging(tmp_path, "prepare", dry_run=True)

    assert os.environ["LITELLM_LOG"] == "DEBUG"


def _make_record(logger_name: str) -> logging.LogRecord:
    return logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=None,
        exc_info=None,
    )


def test_console_handler_filters_muted_third_party_loggers(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    configure_logging(tmp_path, "prepare", dry_run=True)

    root = logging.getLogger()
    console_handlers = [h for h in root.handlers if not isinstance(h, logging.FileHandler)]
    assert len(console_handlers) == 1
    assert console_handlers[0].filter(_make_record("litellm.utils")) is False
    assert console_handlers[0].filter(_make_record("guidami_ai_patente_ingestor.cli"))


def test_file_handler_keeps_muted_third_party_loggers(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    configure_logging(tmp_path, "status", dry_run=False)

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].filter(_make_record("litellm.utils"))
