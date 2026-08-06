from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from commons.repositories.db import QuizReadRepository


def _vector(dimension: int, hot_index: int) -> list[float]:
    """Builds a 1536-dim one-hot vector, distinguishable across variants."""
    vector = [0.0] * dimension
    vector[hot_index] = 1.0
    return vector


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("quiz_question_embeddings", "quiz_questions")
        yield client
        client.truncate("quiz_question_embeddings", "quiz_questions")


def _insert_question(client: PostgresClient, number: str, question_id: int) -> int:
    rows = client.fetch(
        sql.SQL(
            "INSERT INTO quiz_questions (number, question_id, topic, text, correct_answer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id"
        ),
        [number, question_id, "segnaletica", "Domanda di prova?", True],
    )
    return rows[0][0]


def _insert_embedding(
    client: PostgresClient, quiz_question_id: int, variant: str, embedding: list[float]
) -> None:
    client.execute(
        sql.SQL(
            "INSERT INTO quiz_question_embeddings "
            "(quiz_question_id, variant, embedding_3_small) VALUES (%s, %s, %s)"
        ),
        [quiz_question_id, variant, embedding],
    )


@pytest.mark.integration
def test_fetch_with_vectors_joins_only_requested_variant(client: PostgresClient) -> None:
    first_id = _insert_question(client, "0001", 1)
    second_id = _insert_question(client, "0002", 2)
    search_queries_vector = _vector(1536, 0)
    _insert_embedding(client, first_id, "search_queries", search_queries_vector)
    _insert_embedding(client, first_id, "topic_text", _vector(1536, 1))
    _insert_embedding(client, second_id, "topic_text", _vector(1536, 2))

    repository = QuizReadRepository("quiz_questions", "quiz_question_embeddings", client)

    rows = repository.fetch_with_vectors("search_queries")

    assert len(rows) == 1
    assert rows[0].number == "0001"
    assert rows[0].embedding == search_queries_vector
