from collections.abc import Iterator

import pytest
from psycopg import sql
from pydantic import SecretStr

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizQuestionEntity
from guidami_ai_patente_ingestor.repositories import QuizQuestionStoreRepository
from guidami_ai_patente_ingestor.repositories.db.quiz_question_store_repository import (
    _QUIZ_QUESTION_TABLE_COLUMNS,
)


@pytest.fixture
def client() -> Iterator[PostgresClient]:
    config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password=SecretStr("guidami"),
        dbname="guidami_ai_patente",
    )
    with PostgresClient(config) as client:
        client.truncate("quiz_questions")
        yield client
        client.truncate("quiz_questions")


def _question(number: str, image_filename: str | None = None) -> QuizQuestionEntity:
    return QuizQuestionEntity(
        number=number,
        question_id=100,
        topic="Segnaletica",
        text=f"Domanda {number}",
        correct_answer=True,
        image_filename=image_filename,
    )


def _flat_question(**kwargs: object) -> QuizQuestionEntity:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Domanda 1",
        correct_answer=True,
        image_filename=None,
        core_concepts=["Obbligo di precedenza"],
        exact_keywords=["obbligo di precedenza"],
        rule_explanation="Il segnale impone l'obbligo di precedenza.",
        embedding=[0.1, 0.2],
    )
    return QuizQuestionEntity(**{**defaults, **kwargs})


def test_table_columns_are_flat_metadata_columns_without_quiz_metadata() -> None:
    assert _QUIZ_QUESTION_TABLE_COLUMNS == (
        "number",
        "question_id",
        "topic",
        "text",
        "correct_answer",
        "image_filename",
        "core_concepts",
        "exact_keywords",
        "rule_explanation",
        "embedding",
    )


def test_to_db_row_emits_flat_metadata_fields_without_jsonb() -> None:
    question = _flat_question()

    row = QuizQuestionStoreRepository._to_db_row(question)

    assert row == (
        question.number,
        question.question_id,
        question.topic,
        question.text,
        question.correct_answer,
        question.image_filename,
        question.core_concepts,
        question.exact_keywords,
        question.rule_explanation,
        question.embedding,
    )


@pytest.mark.integration
def test_bulk_insert_inserts_questions(client: PostgresClient) -> None:
    repository = QuizQuestionStoreRepository("quiz_questions", client)

    repository.bulk_insert([_question("1"), _question("2", image_filename="abc.jpeg")])

    rows = client.fetch(sql.SQL("SELECT number, image_filename FROM quiz_questions ORDER BY id"))
    assert rows == [("1", None), ("2", "abc.jpeg")]


@pytest.mark.integration
def test_bulk_insert_with_empty_list_is_noop(client: PostgresClient) -> None:
    repository = QuizQuestionStoreRepository("quiz_questions", client)

    repository.bulk_insert([])

    rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert rows == []


@pytest.mark.integration
def test_truncate_empties_table(client: PostgresClient) -> None:
    repository = QuizQuestionStoreRepository("quiz_questions", client)
    repository.bulk_insert([_question("1")])

    repository.truncate()

    rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert rows == []
