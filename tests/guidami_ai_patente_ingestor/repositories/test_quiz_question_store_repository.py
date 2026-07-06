from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.repositories import QuizQuestionStoreRepository


@pytest.fixture
def client() -> Iterator[PostgresClient]:
    config = PostgresConnectionConfig(
        host="localhost",
        port=5432,
        user="guidami",
        password="guidami",
        dbname="guidami_ai_patente",
    )
    with PostgresClient(config) as client:
        client.truncate("quiz_questions")
        yield client
        client.truncate("quiz_questions")


def _question(number: str, image_filename: str | None = None) -> QuizQuestion:
    return QuizQuestion(
        number=number,
        question_id=100,
        topic="Segnaletica",
        text=f"Domanda {number}",
        correct_answer=True,
        image_filename=image_filename,
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
