"""Tests for StoreQuizStep.

Upserts quiz_questions/quiz_images/quiz_question_embeddings, reconciles questions.
"""

from collections.abc import Iterator

import pytest
from flowstep import FlowContext
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizImageEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizVariant, EmbedQuizVariantsResult
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import StoreQuizStep
from guidami_ai_patente_ingestor.repositories import (
    QuizImageStoreRepository,
    QuizQuestionEmbeddingStoreRepository,
    QuizQuestionStoreRepository,
)


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate(
            "quiz_comma_labels", "quiz_labelings", "quiz_question_embeddings", "quiz_questions"
        )
        client.truncate("quiz_images")
        yield client
        client.truncate(
            "quiz_comma_labels", "quiz_labelings", "quiz_question_embeddings", "quiz_questions"
        )
        client.truncate("quiz_images")


def _question(number: str) -> QuizQuestionEntity:
    return QuizQuestionEntity(
        number=number,
        question_id=100,
        topic="Segnaletica",
        text=f"Domanda {number}",
        correct_answer=True,
    )


def _image(filename: str) -> QuizImageEntity:
    return QuizImageEntity(filename=filename, description="Segnale di stop.")


def _make_step(client: PostgresClient) -> StoreQuizStep:
    return StoreQuizStep(
        "store_quiz",
        QuizQuestionStoreRepository("quiz_questions", client),
        QuizImageStoreRepository("quiz_images", client),
        QuizQuestionEmbeddingStoreRepository("quiz_question_embeddings", client),
    )


def _empty_embeddings() -> EmbedQuizVariantsResult:
    return EmbedQuizVariantsResult(variants=[])


def _vector(hot_index: int) -> list[float]:
    """Builds a 1536-dim one-hot vector (matches `embedding_3_small VECTOR(1536)`)."""
    vector = [0.0] * 1536
    vector[hot_index] = 1.0
    return vector


@pytest.mark.integration
def test_store_upserts_questions_and_images_and_resolves_after_rerun(
    client: PostgresClient,
) -> None:
    step = _make_step(client)
    context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [_image("abc.jpeg")],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: _empty_embeddings(),
        }
    )

    step.execute(context)

    question_rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert [row[0] for row in question_rows] == ["1"]

    image_rows = client.fetch(sql.SQL("SELECT filename FROM quiz_images"))
    assert [row[0] for row in image_rows] == ["abc.jpeg"]


@pytest.mark.integration
def test_store_removes_a_question_that_vanished_from_the_input(client: PostgresClient) -> None:
    step = _make_step(client)
    first_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1"), _question("2")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: _empty_embeddings(),
        }
    )
    step.execute(first_context)

    second_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: _empty_embeddings(),
        }
    )
    step.execute(second_context)

    rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert [row[0] for row in rows] == ["1"]


@pytest.mark.integration
def test_store_writes_variant_rows_against_resolved_question_id(client: PostgresClient) -> None:
    step = _make_step(client)
    context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: EmbedQuizVariantsResult(
                variants=[
                    EmbeddableQuizVariant(
                        question_number="1", variant="text", embedding=_vector(0)
                    )
                ]
            ),
        }
    )

    step.execute(context)

    rows = client.fetch(
        sql.SQL(
            "SELECT q.number, e.variant FROM quiz_question_embeddings e "
            "JOIN quiz_questions q ON q.id = e.quiz_question_id"
        )
    )
    assert rows == [("1", "text")]


@pytest.mark.integration
def test_rerun_updates_variant_row_in_place_keeps_one_row(client: PostgresClient) -> None:
    step = _make_step(client)
    first_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: EmbedQuizVariantsResult(
                variants=[
                    EmbeddableQuizVariant(
                        question_number="1", variant="text", embedding=_vector(0)
                    )
                ]
            ),
        }
    )
    step.execute(first_context)

    second_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: EmbedQuizVariantsResult(
                variants=[
                    EmbeddableQuizVariant(
                        question_number="1", variant="text", embedding=_vector(1)
                    )
                ]
            ),
        }
    )
    step.execute(second_context)

    rows = client.fetch(sql.SQL("SELECT embedding_3_small FROM quiz_question_embeddings"))
    assert len(rows) == 1, "expected the variant row to be upserted in place, not duplicated"


@pytest.mark.integration
def test_question_removed_from_input_cascades_its_variant_rows(client: PostgresClient) -> None:
    step = _make_step(client)
    first_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: EmbedQuizVariantsResult(
                variants=[
                    EmbeddableQuizVariant(
                        question_number="1", variant="text", embedding=_vector(0)
                    )
                ]
            ),
        }
    )
    step.execute(first_context)

    second_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
            context_keys.QUIZ_VARIANT_EMBEDDINGS: _empty_embeddings(),
        }
    )
    step.execute(second_context)

    rows = client.fetch(sql.SQL("SELECT * FROM quiz_question_embeddings"))
    assert rows == [], "ON DELETE CASCADE from quiz_questions must remove its variant rows"
