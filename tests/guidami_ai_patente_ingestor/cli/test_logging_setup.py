"""Tests for cli/logging_setup.py."""

import argparse
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from commons.observability import RunArtifactWriter


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


def _prepare_args() -> argparse.Namespace:
    return argparse.Namespace(command="prepare", entity="knowledge", source="cds", force=False)


def _reset_args() -> argparse.Namespace:
    return argparse.Namespace(command="reset", entity="knowledge")


def test_configure_logging_dry_run_creates_no_directory_and_returns_none(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    writer = configure_logging(tmp_path, _prepare_args(), dry_run=True)

    assert writer is None
    assert not (tmp_path / "logs").exists()


def test_configure_logging_creates_run_dir_and_log_file(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    writer = configure_logging(tmp_path, _reset_args(), dry_run=False)

    assert writer is not None
    assert writer.log_file.parent.name.startswith("ingest_reset_")
    # `RunArtifactWriter.__enter__` is not called by `configure_logging` itself anymore,
    # so the log file isn't created until `__enter__`; only the run directory (created
    # eagerly by `build_run_dir` inside `RunArtifactWriter.__init__`) can be asserted here.
    assert writer.run_dir.exists()


def test_configure_logging_avoids_same_minute_collision_with_numeric_suffix(
    tmp_path: Path,
) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    first = configure_logging(tmp_path, _reset_args(), dry_run=False)
    second = configure_logging(tmp_path, _reset_args(), dry_run=False)

    assert first is not None
    assert second is not None
    assert second.run_dir.name == f"{first.run_dir.name}_2"


def test_no_stream_handler_when_console_handler_disabled(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    writer = configure_logging(tmp_path, _prepare_args(), dry_run=False, use_console_handler=False)

    assert writer is not None
    assert isinstance(writer, RunArtifactWriter)
    writer.__enter__()
    try:
        root = logging.getLogger()
        stream_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert stream_handlers == []
        assert len(file_handlers) == 1
    finally:
        writer.__exit__(None, None, None)


def test_configure_logging_defaults_litellm_log_to_warning(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    os.environ.pop("LITELLM_LOG", None)

    configure_logging(tmp_path, _prepare_args(), dry_run=True)

    assert os.environ["LITELLM_LOG"] == "WARNING"


def test_configure_logging_does_not_override_existing_litellm_log(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    os.environ["LITELLM_LOG"] = "DEBUG"

    configure_logging(tmp_path, _prepare_args(), dry_run=True)

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

    configure_logging(tmp_path, _prepare_args(), dry_run=True)

    root = logging.getLogger()
    console_handlers = [h for h in root.handlers if not isinstance(h, logging.FileHandler)]
    assert len(console_handlers) == 1
    assert console_handlers[0].filter(_make_record("litellm.utils")) is False
    assert console_handlers[0].filter(_make_record("guidami_ai_patente_ingestor.cli"))


def test_file_handler_keeps_muted_third_party_loggers(tmp_path: Path) -> None:
    from guidami_ai_patente_ingestor.cli.logging_setup import configure_logging

    writer = configure_logging(tmp_path, _reset_args(), dry_run=False)

    assert writer is not None
    assert isinstance(writer, RunArtifactWriter)
    writer.__enter__()
    try:
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].filter(_make_record("litellm.utils"))
    finally:
        writer.__exit__(None, None, None)
