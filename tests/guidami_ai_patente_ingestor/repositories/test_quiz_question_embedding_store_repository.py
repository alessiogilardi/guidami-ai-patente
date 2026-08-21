from collections.abc import Iterator

import pytest
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizQuestionEmbeddingEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.repositories import (
    QuizQuestionEmbeddingStoreRepository,
    QuizQuestionStoreRepository,
)


def _vector(hot_index: int) -> list[float]:
    """Builds a 1536-dim one-hot vector (matches `embedding_3_small VECTOR(1536)`)."""
    vector = [0.0] * 1536
    vector[hot_index] = 1.0
    return vector


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(
            "quiz_comma_labels", "quiz_labelings", "quiz_question_embeddings", "quiz_questions"
        )
        yield client
        client.truncate(
            "quiz_comma_labels", "quiz_labelings", "quiz_question_embeddings", "quiz_questions"
        )


def _insert_question(client: PostgresClient, number: str = "1") -> int:
    question = QuizQuestionEntity(
        number=number,
        question_id=100,
        topic="Segnaletica",
        text="Il segnale raffigurato preavvisa un incrocio.",
        correct_answer=True,
        image_filename=None,
        core_concepts=["Obbligo di precedenza"],
        exact_keywords=["preavviso di incrocio"],
        rule_explanation="Il segnale preavvisa un incrocio regolato.",
        vector_search_queries=["query uno"],
    )
    ids = QuizQuestionStoreRepository("quiz_questions", client).upsert_returning_ids([question])
    return ids[0]


@pytest.mark.integration
def test_upsert_then_reupsert_keeps_one_row_per_question_and_variant(
    client: PostgresClient,
) -> None:
    question_id = _insert_question(client)
    repository = QuizQuestionEmbeddingStoreRepository("quiz_question_embeddings", client)
    entity_1 = QuizQuestionEmbeddingEntity(
        quiz_question_id=question_id, variant="text", embedding_3_small=_vector(0)
    )
    entity_2 = QuizQuestionEmbeddingEntity(
        quiz_question_id=question_id, variant="text", embedding_3_small=_vector(1)
    )

    repository.upsert([entity_1])
    repository.upsert([entity_2])

    rows = client.fetch(
        sql.SQL(
            "SELECT quiz_question_id, variant, embedding_3_small FROM quiz_question_embeddings"
        )
    )
    assert len(rows) == 1, "expected exactly one row per (quiz_question_id, variant)"
    assert rows[0][0] == question_id
    assert rows[0][1] == "text"


@pytest.mark.integration
def test_upsert_with_empty_list_is_noop(client: PostgresClient) -> None:
    repository = QuizQuestionEmbeddingStoreRepository("quiz_question_embeddings", client)

    repository.upsert([])

    rows = client.fetch(sql.SQL("SELECT quiz_question_id FROM quiz_question_embeddings"))
    assert rows == []
