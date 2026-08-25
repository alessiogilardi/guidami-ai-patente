"""Tests for cli/commands/reset.py (migrated from the retired test_cli.py)."""

import argparse
from unittest.mock import MagicMock, patch

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from guidami_ai_patente_ingestor.cli.commands.reset import run_reset


def _args(entity: str, apply: bool = False, force: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="reset", entity=entity, apply=apply, force=force)


@pytest.mark.integration
def test_reset_knowledge_truncates_the_golden_set_tables_too(
    ingestor_test_config, seeded_labeling
) -> None:
    """FR-17 (AD-28): the widened TRUNCATE reaches all four golden-set-adjacent tables.

    `quiz_comma_labels` references `article_commas`, so the pre-fix, two-table TRUNCATE
    already fails against this schema with a Postgres FK error — this asserts the fix,
    not just a preference.
    """
    run_reset(ingestor_test_config, _args("knowledge", apply=True))

    with PostgresClient(ingestor_test_config.postgres) as client:
        for table in ("quiz_comma_labels", "quiz_labelings", "article_commas", "articles"):
            rows = client.fetch(
                sql.SQL("SELECT count(*) FROM {t}").format(t=sql.Identifier(table))
            )
            assert rows == [(0,)], f"{table} was not truncated"


@pytest.mark.integration
def test_reset_knowledge_refuses_to_destroy_a_validated_labeling(
    ingestor_test_config, seeded_validated_labeling
) -> None:
    """FR-17: a human-validated labeling blocks the wipe unless `--force` is passed."""
    with pytest.raises(SystemExit) as exit_info:
        run_reset(ingestor_test_config, _args("knowledge", apply=True))

    assert exit_info.value.code != 0
    with PostgresClient(ingestor_test_config.postgres) as client:
        rows = client.fetch(sql.SQL("SELECT count(*) FROM quiz_labelings"))
        assert rows == [(1,)], "nothing may be truncated when the guard fires"


@pytest.mark.integration
def test_force_overrides_the_validated_labeling_guard(
    ingestor_test_config, seeded_validated_labeling
) -> None:
    run_reset(ingestor_test_config, _args("knowledge", apply=True, force=True))

    with PostgresClient(ingestor_test_config.postgres) as client:
        rows = client.fetch(sql.SQL("SELECT count(*) FROM quiz_labelings"))
        assert rows == [(0,)]


def test_the_preview_lists_all_four_tables(capsys: pytest.CaptureFixture[str]) -> None:
    run_reset(config=None, args=_args("knowledge"))  # type: ignore[arg-type]

    output = capsys.readouterr().out
    for table in ("quiz_comma_labels", "quiz_labelings", "article_commas", "articles"):
        assert table in output


def test_run_reset_without_apply_never_opens_a_postgres_connection() -> None:
    args = argparse.Namespace(command="reset", entity="knowledge", apply=False, force=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"
    ) as pg:
        run_reset(MagicMock(), args)

    pg.assert_not_called()


def test_reset_quiz_truncates_embeddings_and_questions_in_one_statement() -> None:
    """T-5 (FR-3): the quiz branch truncates both tables in one combined statement.

    Mirrors the knowledge branch — `quiz_question_embeddings`'s FK references
    `quiz_questions`, so a single-table TRUNCATE fails. Unchanged by Task 9 (D5/D15):
    `reset quiz` has the identical multi-table-FK bug the knowledge branch was fixed
    for, but fixing it is out of scope here.
    """
    args = argparse.Namespace(command="reset", entity="quiz", apply=True)
    config_mock = MagicMock()
    config_mock.quiz_question_embeddings_table = "quiz_question_embeddings"
    config_mock.quiz_questions_table = "quiz_questions"
    mock_client = MagicMock()

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client",
        return_value=mock_client,
    ):
        run_reset(config_mock, args)

    mock_client.truncate.assert_called_once_with("quiz_question_embeddings", "quiz_questions")


def test_reset_quiz_preview_names_both_tables(capsys: pytest.CaptureFixture[str]) -> None:
    """T-5 (FR-3): the preview names both tables, no DB connection opened."""
    args = argparse.Namespace(command="reset", entity="quiz", apply=False)

    with patch(
        "guidami_ai_patente_ingestor.cli.commands.reset.wiring.build_postgres_client"
    ) as pg:
        run_reset(MagicMock(), args)

    output = capsys.readouterr().out
    assert "quiz_questions" in output
    assert "quiz_question_embeddings" in output
    pg.assert_not_called()
