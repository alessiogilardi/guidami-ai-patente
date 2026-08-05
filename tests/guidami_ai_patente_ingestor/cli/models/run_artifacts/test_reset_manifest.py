"""Tests for cli/models/run_artifacts/reset_manifest.py."""

import json

from guidami_ai_patente_ingestor.cli.models.run_artifacts import ResetManifest


def test_model_dump_json_has_only_entity_and_started_at() -> None:
    manifest = ResetManifest(entity="knowledge")

    dumped = json.loads(manifest.model_dump_json(exclude_none=True))

    assert set(dumped) == {"entity", "started_at"}
