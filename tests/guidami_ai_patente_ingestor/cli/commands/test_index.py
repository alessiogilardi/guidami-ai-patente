"""Tests for cli/commands/index.py (migrated from the retired test_cli.py)."""

import argparse
from unittest.mock import MagicMock, patch


def test_run_index_knowledge_builds_flow_with_source_and_runs() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds")
    flow = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_knowledge_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args)

    assert build.call_args.kwargs["source"] == "cds"
    flow.run.assert_called_once()


def test_run_index_quiz_builds_flow_and_runs() -> None:
    args = argparse.Namespace(entity="quiz")
    flow = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_quiz_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args)

    build.assert_called_once()
    flow.run.assert_called_once()
