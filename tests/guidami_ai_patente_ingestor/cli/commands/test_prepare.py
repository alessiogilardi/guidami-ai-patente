"""Tests for cli/commands/prepare.py (migrated from the retired test_cli.py).

`dispatch_prepare` is tested directly with a hand-built `argparse.Namespace`
(argument parsing itself is covered by `cli/test_parser.py`). `run_prepare`
covers the Postgres-degradation path (tracker=None on connection failure).
"""

import argparse
import logging
from unittest.mock import MagicMock, patch

import psycopg
import pytest


def _make_config_mock() -> MagicMock:
    """Return a minimal IngestorConfig mock with valid source catalogs."""
    config = MagicMock()
    config.knowledge_preparation.output_layer = "enriched"
    config.quiz_preparation.sources = ["quiz"]
    config.quiz_preparation.output_layer = "enriched"
    return config


def test_dispatch_prepare_knowledge_runs_both_preparation_flows() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(config_mock, MagicMock(), MagicMock(), args, tracker=None)

    build_clean.assert_called_once()
    build_enrich.assert_called_once()
    assert run_prep.call_count == 2


def test_dispatch_prepare_knowledge_passes_source_to_factories() -> None:
    args = argparse.Namespace(entity="knowledge", source="cap", force=False)
    config_mock = _make_config_mock()

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(config_mock, MagicMock(), MagicMock(), args, tracker=None)

    assert build_clean.call_args.kwargs["source"] == "cap"
    assert build_enrich.call_args.kwargs["source"] == "cap"


def test_dispatch_prepare_knowledge_with_force_passes_force_true_to_runner() -> None:
    args = argparse.Namespace(entity="knowledge", source="cds", force=True)
    config_mock = _make_config_mock()

    with (
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.prepare.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ),
        patch("guidami_ai_patente_ingestor.cli.commands.prepare.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli.commands.prepare import dispatch_prepare

        dispatch_prepare(config_mock, MagicMock(), MagicMock(), args, tracker=None)

    for c in run_prep.call_args_list:
        force = c.kwargs.get("force") if "force" in c.kwargs else c.args[2]
        assert force is True, f"expected force=True when args.force is True, got {force!r}"


def test_dispatch_prepare_quiz_runs_both_preparation_flows() -> None:
    args = argparse.Namespace(entity="quiz", force=False)
    config_mock = _make_config_mock()

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

        dispatch_prepare(config_mock, MagicMock(), MagicMock(), args, tracker=None)

    build_clean.assert_called_once()
    build_enrich.assert_called_once()
    assert run_prep.call_count == 2


def test_run_prepare_degrades_without_postgres(caplog: pytest.LogCaptureFixture) -> None:
    """When the tracking Postgres client fails to build, prepare dispatches with tracker=None."""
    args = argparse.Namespace(entity="knowledge", source="cds", force=False)
    config_mock = _make_config_mock()

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

        run_prepare(config_mock, MagicMock(), MagicMock(), args)

    assert dispatch_mock.call_args.kwargs.get("tracker") is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)
