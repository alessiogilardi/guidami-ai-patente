"""Tests for cli/commands/reset.py (migrated from the retired test_cli.py)."""

import argparse
from unittest.mock import MagicMock, patch

import pytest


def test_reset_knowledge_truncates_both_tables_commas_first() -> None:
    """T-16 (FR-12): the knowledge branch truncates both tables in one combined statement.

    Per PD-13 (plans/0001-article-level-storage-plan.md): Postgres refuses to TRUNCATE
    `articles` while `article_commas`'s FK references it unless both tables are named
    in the SAME TRUNCATE statement — two separate sequential `.truncate()` calls (one
    per repository) fail against a real Postgres regardless of ordering. The knowledge
    branch must therefore call `PostgresClient.truncate(*table_names)` directly, with
    the child table named first, not go through per-table repository `.truncate()`.
    """
    args = argparse.Namespace(entity="knowledge", apply=True)
    config_mock = MagicMock()
    config_mock.article_commas_table = "article_commas"
    config_mock.articles_table = "articles"
    mock_client = MagicMock()

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client",
        return_value=mock_client,
    ):
        from guidami_ai_patente_ingestor.cli.commands.reset import run_reset

        run_reset(config_mock, args)

    mock_client.truncate.assert_called_once_with("article_commas", "articles")


def test_reset_knowledge_preview_names_both_tables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """T-16 (FR-12): the preview names both tables, no DB connection opened."""
    args = argparse.Namespace(entity="knowledge", apply=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"
    ) as pg:
        from guidami_ai_patente_ingestor.cli.commands.reset import run_reset

        run_reset(MagicMock(), args)

    output = capsys.readouterr().out
    assert "articles" in output
    assert "article_commas" in output
    pg.assert_not_called()


def test_run_reset_without_apply_never_opens_a_postgres_connection() -> None:
    args = argparse.Namespace(entity="knowledge", apply=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"
    ) as pg:
        from guidami_ai_patente_ingestor.cli.commands.reset import run_reset

        run_reset(MagicMock(), args)

    pg.assert_not_called()


def test_run_reset_quiz_calls_quiz_question_truncate() -> None:
    args = argparse.Namespace(entity="quiz", apply=True)
    config_mock = MagicMock()
    mock_repo_class = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.reset.QuizQuestionStoreRepository",
            mock_repo_class,
        ),
    ):
        from guidami_ai_patente_ingestor.cli.commands.reset import run_reset

        run_reset(config_mock, args)

    mock_repo_class.return_value.truncate.assert_called_once()
