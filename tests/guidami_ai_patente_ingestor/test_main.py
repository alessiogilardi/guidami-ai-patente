"""Smoke test per l'entrypoint `ingest-knowledge` (main) — per-source."""

import sys
from unittest.mock import MagicMock, patch

import pytest


def test_main_builds_per_source_flow_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest-knowledge", "--source", "cds"])
    flow = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.main.IngestorConfig"),
        patch("guidami_ai_patente_ingestor.main.LayerResolver"),
        patch("guidami_ai_patente_ingestor.main.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.main.PostgresClient"),
        patch(
            "guidami_ai_patente_ingestor.main.build_knowledge_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.main import main

        main()

    assert build.call_args.kwargs["source"] == "cds"
    flow.run.assert_called_once()


def test_main_requires_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest-knowledge"])

    from guidami_ai_patente_ingestor.main import main

    with pytest.raises(SystemExit):
        main()
