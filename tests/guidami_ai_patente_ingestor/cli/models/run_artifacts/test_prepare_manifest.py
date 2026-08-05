"""Tests for cli/models/run_artifacts/prepare_manifest.py."""

import json

from guidami_ai_patente_ingestor.cli.models.run_artifacts import PrepareManifest


def test_model_dump_json_omits_source_for_quiz() -> None:
    manifest = PrepareManifest(entity="quiz", force=True)

    dumped = json.loads(manifest.model_dump_json(exclude_none=True))

    assert "source" not in dumped
    assert dumped["entity"] == "quiz"
    assert dumped["force"] is True
    assert dumped["flows"] == []


def test_model_dump_json_includes_source_for_knowledge() -> None:
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    dumped = json.loads(manifest.model_dump_json(exclude_none=True))

    assert dumped["source"] == "cds"


def test_record_flow_appends_in_order() -> None:
    manifest = PrepareManifest(entity="quiz", force=False)

    manifest.record_flow("quiz_cleaning")
    manifest.record_flow("quiz_enrichment")

    assert manifest.flows == ["quiz_cleaning", "quiz_enrichment"]
