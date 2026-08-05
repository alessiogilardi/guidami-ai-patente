"""Tests for commons/observability/run_artifact_writer/models/run_manifest.py."""

from datetime import UTC, datetime

import pytest

from commons.observability import RunManifest


def test_to_report_lines_raises_not_implemented_when_not_overridden() -> None:
    manifest = RunManifest()

    with pytest.raises(NotImplementedError):
        manifest.to_report_lines()


def test_started_at_defaults_to_now_utc() -> None:
    manifest = RunManifest()

    assert manifest.started_at.tzinfo is not None
    assert abs((datetime.now(UTC) - manifest.started_at).total_seconds()) < 5
