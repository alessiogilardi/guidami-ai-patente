"""Tests for commons/observability/run_artifact_writer/run_artifact_writer.py."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from commons.observability import RunArtifactWriter, RunArtifactWriterConfig


@pytest.fixture(autouse=True)
def _reset_root_handlers() -> Iterator[None]:
    """Isolates each test from the global root-logger state `__enter__` mutates.

    Closes any handler added during the test (the `FileHandler` `__enter__` installs)
    before restoring the original handler list, so the underlying log file is not left
    open -- an open handle would block pytest's `tmp_path` cleanup on Windows.
    """
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    yield
    for handler in root.handlers:
        if handler not in original_handlers:
            handler.close()
    root.handlers[:] = original_handlers


def _config(tmp_path: Path) -> RunArtifactWriterConfig:
    return RunArtifactWriterConfig(
        logs_root=tmp_path,
        source="reg",
        toc_url="http://toc",
        output_path=Path("data/parsed/reg/x.json"),
    )


def test_build_run_dir_avoids_same_minute_collision_with_numeric_suffix(
    tmp_path: Path,
) -> None:
    first = RunArtifactWriter.build_run_dir(tmp_path, "scrape_reg")
    second = RunArtifactWriter.build_run_dir(tmp_path, "scrape_reg")

    assert second.name == f"{first.name}_2"


def test_exit_writes_manifest_and_report_with_counts_and_skips(tmp_path: Path) -> None:
    with RunArtifactWriter(_config(tmp_path)) as writer:
        writer.set_found(3)
        writer.record_saved()
        writer.record_skip("parse_error", "Art. 5", "boom")

    manifest = json.loads((writer.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["found"] == 3
    assert manifest["saved"] == 1
    assert manifest["skipped"] == {
        "fetch_failed": 0,
        "session_invalid": 0,
        "parse_error": 1,
    }

    report = (writer.run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Parse errors\n\n- Art. 5: boom" in report
    assert "## Fetch failures\n\nNone" in report


def test_exit_writes_artifacts_even_when_the_with_block_raises(tmp_path: Path) -> None:
    writer = RunArtifactWriter(_config(tmp_path))

    with pytest.raises(ValueError, match="boom"), writer:
        writer.set_found(1)
        raise ValueError("boom")

    assert (writer.run_dir / "manifest.json").exists()
    assert (writer.run_dir / "report.md").exists()
    manifest = json.loads((writer.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["found"] == 1
