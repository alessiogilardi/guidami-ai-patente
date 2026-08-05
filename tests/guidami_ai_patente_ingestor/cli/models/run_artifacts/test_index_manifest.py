"""Tests for cli/models/run_artifacts/index_manifest.py."""

import json

from guidami_ai_patente_ingestor.cli.models.run_artifacts import IndexManifest


def test_model_dump_json_omits_source_for_quiz() -> None:
    manifest = IndexManifest(entity="quiz")

    dumped = json.loads(manifest.model_dump_json(exclude_none=True))

    assert "source" not in dumped
    assert dumped["entity"] == "quiz"
    assert dumped["flows"] == []


def test_model_dump_json_includes_source_for_knowledge() -> None:
    manifest = IndexManifest(entity="knowledge", source="cds")

    dumped = json.loads(manifest.model_dump_json(exclude_none=True))

    assert dumped["source"] == "cds"


def test_index_manifest_has_no_force_field() -> None:
    assert hasattr(IndexManifest, "force") is False
