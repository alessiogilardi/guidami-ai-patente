"""Tests for cli.py (SP07 — unified `ingest` CLI with subcommands).

Each test patches the dependencies of cli.py at the module level and verifies
that the correct factory / runner / repository methods are invoked depending on
the subcommand parsed from sys.argv.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import psycopg
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_mock() -> MagicMock:
    """Return a minimal IngestorConfig mock with valid source catalogs."""
    config = MagicMock()
    config.knowledge_preparation.sources = ["cds", "cap"]
    config.knowledge_indexing.sources = ["cds", "cap"]
    config.quiz_preparation.sources = ["quiz"]
    config.quiz_indexing.sources = ["quiz"]
    return config


# ---------------------------------------------------------------------------
# prepare knowledge
# ---------------------------------------------------------------------------


def test_prepare_knowledge_runs_both_preparation_flows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "knowledge", "--source", "cds"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    build_clean.assert_called_once()
    build_enrich.assert_called_once()
    assert run_prep.call_count == 2


def test_prepare_knowledge_passes_source_to_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "knowledge", "--source", "cap"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    assert build_clean.call_args.kwargs["source"] == "cap"
    assert build_enrich.call_args.kwargs["source"] == "cap"


def test_prepare_knowledge_default_force_is_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "knowledge", "--source", "cds"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ),
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    for c in run_prep.call_args_list:
        force = (
            c.kwargs.get("force")
            if "force" in c.kwargs
            else (c.args[2] if len(c.args) > 2 else None)
        )
        assert force is False, f"expected force=False by default, got {force!r}"


def test_prepare_knowledge_with_force_passes_force_true_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["ingest", "prepare", "knowledge", "--source", "cds", "--force"]
    )
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ),
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    for c in run_prep.call_args_list:
        force = (
            c.kwargs.get("force")
            if "force" in c.kwargs
            else (c.args[2] if len(c.args) > 2 else None)
        )
        assert force is True, f"expected force=True when --force is passed, got {force!r}"


def test_prepare_knowledge_requires_source_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "knowledge"])

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig"),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch("guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow"),
        patch("guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow"),
        patch("guidami_ai_patente_ingestor.cli.run_preparation"),
    ):
        from guidami_ai_patente_ingestor.cli import main

        with pytest.raises(SystemExit):
            main()


def test_prepare_degrades_without_postgres(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """When PostgresClient construction fails, prepare still dispatches with tracker=None."""
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "knowledge", "--source", "cds"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.PostgresClient",
            side_effect=psycopg.OperationalError("connection refused"),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
        caplog.at_level(logging.WARNING),
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    assert run_prep.call_count == 2
    assert build_enrich.call_args.kwargs["tracker"] is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


# ---------------------------------------------------------------------------
# index knowledge
# ---------------------------------------------------------------------------


def test_index_knowledge_builds_flow_with_source_and_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "index", "knowledge", "--source", "cds"])
    config_mock = _make_config_mock()
    flow = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch("guidami_ai_patente_ingestor.cli.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.PostgresClient"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_knowledge_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    assert build.call_args.kwargs["source"] == "cds"
    flow.run.assert_called_once()


def test_index_knowledge_requires_source_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "index", "knowledge"])

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig"),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch("guidami_ai_patente_ingestor.cli.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.PostgresClient"),
        patch("guidami_ai_patente_ingestor.cli.build_knowledge_indexing_flow"),
    ):
        from guidami_ai_patente_ingestor.cli import main

        with pytest.raises(SystemExit):
            main()


# ---------------------------------------------------------------------------
# prepare quiz
# ---------------------------------------------------------------------------


def test_prepare_quiz_runs_both_preparation_flows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "quiz"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_quiz_cleaning_flow",
            return_value=MagicMock(),
        ) as build_clean,
        patch(
            "guidami_ai_patente_ingestor.cli.build_quiz_enrichment_flow",
            return_value=MagicMock(),
        ) as build_enrich,
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    build_clean.assert_called_once()
    build_enrich.assert_called_once()
    assert run_prep.call_count == 2


def test_prepare_quiz_with_force_passes_force_true_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "prepare", "quiz", "--force"])
    config_mock = _make_config_mock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_quiz_cleaning_flow",
            return_value=MagicMock(),
        ),
        patch(
            "guidami_ai_patente_ingestor.cli.build_quiz_enrichment_flow",
            return_value=MagicMock(),
        ),
        patch("guidami_ai_patente_ingestor.cli.run_preparation") as run_prep,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    for c in run_prep.call_args_list:
        force = (
            c.kwargs.get("force")
            if "force" in c.kwargs
            else (c.args[2] if len(c.args) > 2 else None)
        )
        assert force is True, f"expected force=True when --force is passed, got {force!r}"


# ---------------------------------------------------------------------------
# index quiz
# ---------------------------------------------------------------------------


def test_index_quiz_builds_flow_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "index", "quiz"])
    config_mock = _make_config_mock()
    flow = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.LayerResolver"),
        patch("guidami_ai_patente_ingestor.cli.LiteLLMEmbeddingClient"),
        patch("guidami_ai_patente_ingestor.cli.PostgresClient"),
        patch(
            "guidami_ai_patente_ingestor.cli.build_quiz_indexing_flow",
            return_value=flow,
        ) as build,
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    build.assert_called_once()
    flow.run.assert_called_once()


# ---------------------------------------------------------------------------
# reset knowledge
# ---------------------------------------------------------------------------


def test_reset_knowledge_calls_knowledge_chunk_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "reset", "knowledge"])
    config_mock = _make_config_mock()
    mock_repo_class = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.PostgresClient"),
        patch(
            "guidami_ai_patente_ingestor.cli.KnowledgeChunkStoreRepository",
            mock_repo_class,
        ),
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    mock_repo_class.return_value.truncate.assert_called_once()


# ---------------------------------------------------------------------------
# reset quiz
# ---------------------------------------------------------------------------


def test_reset_quiz_calls_quiz_question_truncate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ingest", "reset", "quiz"])
    config_mock = _make_config_mock()
    mock_repo_class = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.IngestorConfig", return_value=config_mock),
        patch("guidami_ai_patente_ingestor.cli.PostgresClient"),
        patch(
            "guidami_ai_patente_ingestor.cli.QuizQuestionStoreRepository",
            mock_repo_class,
        ),
    ):
        from guidami_ai_patente_ingestor.cli import main

        main()

    mock_repo_class.return_value.truncate.assert_called_once()
