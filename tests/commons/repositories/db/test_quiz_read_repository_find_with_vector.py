"""The single-row vector read the live labeling path is driven by (spec 0012, FR-6)."""

from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.repositories.db import QuizReadRepository
from labeling import EMBEDDING_MODEL_COLUMN

# `quiz_labelings`/`quiz_comma_labels` are not otherwise used by this test, but
# both hold a live FK back to `quiz_questions` (via `quiz_labelings`), and Postgres
# refuses to TRUNCATE a table referenced by a FK unless the referencing table is
# truncated in the same statement — see `PostgresClient.truncate`'s docstring.
_TABLES = (
    "quiz_comma_labels",
    "quiz_labelings",
    "quiz_question_embeddings",
    "quiz_answers",
    "quiz_questions",
    "quiz_images",
)


@pytest.fixture
def seeded(postgres_test_config: PostgresConnectionConfig) -> Iterator[QuizReadRepository]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(*_TABLES)
        client.execute(
            sql.SQL("INSERT INTO quiz_images (filename, description) VALUES (%s, %s)"),
            ["S0142.png", "Segnale di divieto di sosta"],
        )
        rows = client.fetch(
            sql.SQL(
                "INSERT INTO quiz_questions "
                "(number, question_id, topic, text, correct_answer, image_filename) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
            ),
            ["0001", 1, "segnaletica", "Il segnale vieta la sosta?", True, "S0142.png"],
        )
        question_id = int(rows[0][0])
        client.execute(
            sql.SQL(
                "INSERT INTO quiz_question_embeddings "
                "(quiz_question_id, variant, {column}) VALUES (%s, %s, %s::vector)"
            ).format(column=sql.Identifier(EMBEDDING_MODEL_COLUMN)),
            [question_id, "topic_text", [0.1] * 1536],
        )
        yield QuizReadRepository(
            "quiz_questions", "quiz_question_embeddings", "quiz_images", client
        )
        client.truncate(*_TABLES)


@pytest.mark.integration
def test_the_row_carries_the_vector_and_the_image_description(
    seeded: QuizReadRepository,
) -> None:
    row = seeded.find_with_vector("0001", "topic_text", EMBEDDING_MODEL_COLUMN)

    assert row is not None
    assert (row.number, row.correct_answer, row.image_description) == (
        "0001",
        True,
        "Segnale di divieto di sosta",
    )
    assert len(row.embedding) == 1536


@pytest.mark.integration
def test_an_unknown_number_is_absent(seeded: QuizReadRepository) -> None:
    assert seeded.find_with_vector("9999", "topic_text", EMBEDDING_MODEL_COLUMN) is None


@pytest.mark.integration
def test_a_variant_with_no_vector_is_absent(seeded: QuizReadRepository) -> None:
    """FR-7's not_indexed case: absence, never a row carrying a null embedding."""
    assert seeded.find_with_vector("0001", "combined_description", EMBEDDING_MODEL_COLUMN) is None
