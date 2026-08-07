from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizQuestionEntity
from guidami_ai_patente_ingestor.repositories import QuizQuestionStoreRepository
from guidami_ai_patente_ingestor.repositories.db.quiz_question_store_repository import (
    _QUIZ_QUESTION_TABLE_COLUMNS,
)


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("quiz_question_embeddings", "quiz_questions")
        yield client
        client.truncate("quiz_question_embeddings", "quiz_questions")


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
        vector_search_queries=["query"],
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
        "vector_search_queries",
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
        question.vector_search_queries,
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
def test_upsert_updates_in_place_and_keeps_the_id(client: PostgresClient) -> None:
    repository = QuizQuestionStoreRepository("quiz_questions", client)
    repository.upsert([_question("1")])
    question_id = client.fetch(sql.SQL("SELECT id FROM quiz_questions WHERE number = %s"), ["1"])[
        0
    ][0]

    repository.upsert([_question("1").model_copy(update={"text": "Domanda 1 aggiornata"})])

    rows = client.fetch(sql.SQL("SELECT id, text FROM quiz_questions WHERE number = %s"), ["1"])
    assert len(rows) == 1, "re-upserting the same natural key must not insert a second row"
    assert rows[0][0] == question_id, "the id must stay stable across an upsert of the same key"
    assert rows[0][1] == "Domanda 1 aggiornata"


@pytest.mark.integration
def test_delete_missing_removes_only_absent_numbers(client: PostgresClient) -> None:
    repository = QuizQuestionStoreRepository("quiz_questions", client)
    kept = _question("1")
    repository.upsert([kept, _question("2")])

    repository.delete_missing([kept])

    rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert [row[0] for row in rows] == ["1"]
