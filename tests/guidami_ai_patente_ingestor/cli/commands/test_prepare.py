"""Tests for cli/commands/prepare.py (migrated from the retired test_cli.py).

`dispatch_prepare` is tested directly with a hand-built `argparse.Namespace`
(argument parsing itself is covered by `cli/test_parser.py`). `run_prepare`
covers the Postgres-degradation path (tracker=None on connection failure).
"""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import psycopg
import pytest

from guidami_ai_patente_ingestor.cli.models.run_artifacts import PrepareManifest

if TYPE_CHECKING:
    # See test_embedding_service.py for why this import is TYPE_CHECKING-guarded.
    from tests.conftest import RecordingProgressReporter


def _make_config_mock() -> MagicMock:
    """Return a minimal IngestorConfig mock with valid source catalogs."""
    config = MagicMock()
    config.knowledge_preparation.output_layer = "enriched"
    config.quiz_preparation.sources = ["quiz"]
    config.quiz_preparation.output_layer = "enriched"
    return config


def test_dispatch_prepare_knowledge_runs_directly_without_run_preparation() -> None:
    """Decision 11: the knowledge branch always runs; no coarse run_preparation skip."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()
    clean_flow_mock = MagicMock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=clean_flow_mock,
        ) as build_clean,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    build_clean.assert_called_once()
    clean_flow_mock.run.assert_called_once()
    run_prep.assert_not_called()


def test_dispatch_prepare_knowledge_passes_source_to_factory() -> None:
    args = argparse.Namespace(entity="knowledge", source="cap", force=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="knowledge", source="cap", force=False)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    assert build_clean.call_args.kwargs["source"] == "cap"


def test_dispatch_prepare_knowledge_with_force_passes_force_to_the_flow_factory() -> None:
    """`force` now threads into the flow factory (FilterAlreadyDoneStep), not run_preparation."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=True)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=True)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    assert build_clean.call_args.kwargs["force"] is True


def test_dispatch_prepare_knowledge_runs_only_cleaning() -> None:
    """FR-16/AD-18 (T-13): the knowledge branch no longer builds/runs an enrichment flow."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()
    clean_flow_mock = MagicMock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
        return_value=clean_flow_mock,
    ) as build_clean:
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    build_clean.assert_called_once()
    clean_flow_mock.run.assert_called_once()

    from guidami_ai_patente_ingestor.cli.commands import prepare as prepare_module

    assert not hasattr(prepare_module, "build_knowledge_enrichment_flow")


def test_dispatch_prepare_quiz_runs_both_preparation_flows() -> None:
    args = argparse.Namespace(entity="quiz", force=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="quiz", force=False)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_quiz_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_quiz_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    build_clean.assert_called_once()
    build_enrich.assert_called_once()
    assert run_prep.call_count == 2


def test_knowledge_branch_records_flow_on_manifest() -> None:
    """FR-4: the knowledge branch records "knowledge_cleaning" onto the manifest."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
        return_value=MagicMock(),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    assert manifest.flows == ["knowledge_cleaning"]


def test_quiz_branch_records_both_flows_in_order() -> None:
    """FR-4: the quiz branch records both flows on the manifest, in run order."""
    args = argparse.Namespace(entity="quiz", force=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="quiz", force=False)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_quiz_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_quiz_enrichment_flow",
            return_value=MagicMock(),
        ),
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=MagicMock(),
        )

    assert manifest.flows == ["quiz_cleaning", "quiz_enrichment"]


def test_run_prepare_degrades_without_postgres(caplog: pytest.LogCaptureFixture) -> None:
    """When the tracking Postgres client fails to build, prepare dispatches with tracker=None."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=False, dry_run=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.wiring.build_postgres_client",
            side_effect=psycopg.OperationalError("connection refused"),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.dispatch_prepare"
        ) as dispatch_mock,
        caplog.at_level(logging.WARNING),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import run_prepare

        run_prepare(config_mock, MagicMock(), MagicMock(), args, manifest, progress=MagicMock())

    assert dispatch_mock.call_args.kwargs.get("tracker") is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_run_prepare_dry_run_never_touches_postgres_or_dispatches() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", force=False, dry_run=True)
    config_mock = _make_config_mock()

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.wiring.build_postgres_client"
        ) as pg,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.dispatch_prepare"
        ) as dispatch_mock,
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import run_prepare

        run_prepare(config_mock, MagicMock(), MagicMock(), args, None, progress=MagicMock())

    pg.assert_not_called()
    dispatch_mock.assert_not_called()


def test_knowledge_branch_brackets_the_cleaning_flow(
    progress_recorder: RecordingProgressReporter,
) -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()
    manifest = PrepareManifest(entity="knowledge", source="cds", force=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
        return_value=MagicMock(),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(
            config_mock,
            MagicMock(),
            MagicMock(),
            args,
            tracker=None,
            manifest=manifest,
            progress=progress_recorder,
        )

    assert progress_recorder.calls == [
        ("begin_run", (1,)),
        ("begin_flow", ("knowledge_cleaning",)),
        ("end_flow", ()),
    ]


def test_dry_run_emits_no_progress_calls(
    progress_recorder: RecordingProgressReporter,
) -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", force=False, dry_run=True)
    config_mock = _make_config_mock()

    from guidami_ai_patente_ingestor.cli.commands.prepare import run_prepare

    run_prepare(config_mock, MagicMock(), MagicMock(), args, None, progress=progress_recorder)

    assert progress_recorder.calls == []
