"""Tests for cli/commands/index.py (migrated from the retired test_cli.py)."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from guidami_ai_patente_ingestor.cli.models.run_artifacts import IndexManifest

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter


def test_run_index_knowledge_builds_flow_with_source_and_runs() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", dry_run=False)
    flow = MagicMock()
    manifest = IndexManifest(entity="knowledge", source="cds")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_knowledge_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, manifest, progress=MagicMock())

    assert build.call_args.kwargs["source"] == "cds"
    flow.run.assert_called_once()


def test_run_index_quiz_builds_flow_and_runs() -> None:
    args = argparse.Namespace(entity="quiz", dry_run=False)
    flow = MagicMock()
    manifest = IndexManifest(entity="quiz")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_quiz_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, manifest, progress=MagicMock())

    build.assert_called_once()
    flow.run.assert_called_once()


def test_run_index_dry_run_never_touches_postgres_or_builds_a_flow() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", dry_run=True)

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client") as pg,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_knowledge_indexing_flow"
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, None, progress=MagicMock())

    pg.assert_not_called()
    build.assert_not_called()


def test_knowledge_branch_brackets_the_flow(
    progress_recorder: RecordingProgressReporter,
) -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", dry_run=False)
    flow = MagicMock()
    manifest = IndexManifest(entity="knowledge", source="cds")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_knowledge_indexing_flow",
            return_value=flow,
        ),
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, manifest, progress=progress_recorder)

    assert progress_recorder.calls == [
        ("begin_run", (1,)),
        ("begin_flow", ("knowledge_indexing",)),
        ("end_flow", ()),
    ]


def test_index_dry_run_emits_no_progress_calls(
    progress_recorder: RecordingProgressReporter,
) -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", dry_run=True)

    from guidami_ai_patente_ingestor.cli.commands.index import run_index

    run_index(MagicMock(), MagicMock(), args, None, progress=progress_recorder)

    assert progress_recorder.calls == []


def test_knowledge_branch_records_flow_on_manifest() -> None:
    """FR-4: the knowledge branch records "knowledge_indexing" onto the manifest."""
    args = argparse.Namespace(entity="knowledge", source="cds", dry_run=False)
    manifest = IndexManifest(entity="knowledge", source="cds")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_knowledge_indexing_flow",
            return_value=MagicMock(),
        ),
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, manifest, progress=MagicMock())

    assert manifest.flows == ["knowledge_indexing"]


def test_quiz_branch_records_flow_on_manifest() -> None:
    """FR-4: the quiz branch records "quiz_indexing" onto the manifest."""
    args = argparse.Namespace(entity="quiz", dry_run=False)
    manifest = IndexManifest(entity="quiz")

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.index.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.commands.index.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.index.build_quiz_indexing_flow",
            return_value=MagicMock(),
        ),
    ):
        from guidami_ai_patente_ingestor.cli.commands.index import run_index

        run_index(MagicMock(), MagicMock(), args, manifest, progress=MagicMock())

    assert manifest.flows == ["quiz_indexing"]
