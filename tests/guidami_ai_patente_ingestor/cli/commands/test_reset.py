"""Tests for cli/commands/reset.py (migrated from the retired test_cli.py)."""

import argparse
from unittest.mock import MagicMock, patch


def test_run_reset_knowledge_calls_knowledge_chunk_truncate() -> None:
    args = argparse.Namespace(entity="knowledge")
    config_mock = MagicMock()
    mock_repo_class = MagicMock()

    with (
        patch("guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"),
        patch(
            "guidami_ai_patente_ingestor.cli.commands.reset.KnowledgeChunkStoreRepository",
            mock_repo_class,
        ),
    ):
        from guidami_ai_patente_ingestor.cli.commands.reset import run_reset

        run_reset(config_mock, args)

    mock_repo_class.return_value.truncate.assert_called_once()


def test_run_reset_quiz_calls_quiz_question_truncate() -> None:
    args = argparse.Namespace(entity="quiz")
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
