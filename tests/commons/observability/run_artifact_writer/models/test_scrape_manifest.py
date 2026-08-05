"""Tests for commons/observability/run_artifact_writer/models/scrape_manifest.py."""

import json
from datetime import UTC, datetime
from pathlib import Path

from commons.observability import ScrapeManifest


def _manifest() -> ScrapeManifest:
    manifest = ScrapeManifest(
        source="reg", toc_url="http://toc", output_path=Path("data/parsed/reg/x.json")
    )
    manifest.set_found(3)
    manifest.record_saved()
    manifest.record_skip("parse_error", "Art. 5", "boom")
    return manifest


def test_model_dump_json_matches_todays_manifest_shape() -> None:
    manifest = _manifest()
    manifest.ended_at = datetime.now(UTC)

    dumped = json.loads(manifest.model_dump_json())

    assert dumped["found"] == 3
    assert dumped["saved"] == 1
    assert dumped["skipped"] == {"fetch_failed": 0, "session_invalid": 0, "parse_error": 1}
    assert dumped["source"] == "reg"
    assert dumped["output_path"] == str(Path("data/parsed/reg/x.json"))
    assert datetime.fromisoformat(dumped["started_at"]) == manifest.started_at


def test_to_report_lines_matches_todays_report_shape() -> None:
    manifest = _manifest()

    report = "\n".join(manifest.to_report_lines())

    assert "## Parse errors\n\n- Art. 5: boom" in report
    assert "## Fetch failures\n\nNone" in report
