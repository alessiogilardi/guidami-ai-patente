"""Tests for StoreQuizStep (upserts quiz_questions/quiz_images, reconciles questions)."""

from collections.abc import Iterator

import pytest
from flowstep import FlowContext
from psycopg import sql

from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig
from domain.entities.quiz import QuizImageEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import StoreQuizStep
from guidami_ai_patente_ingestor.repositories import (
    QuizImageStoreRepository,
    QuizQuestionStoreRepository,
)


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("quiz_question_embeddings", "quiz_questions")
        client.truncate("quiz_images")
        yield client
        client.truncate("quiz_question_embeddings", "quiz_questions")
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


@pytest.mark.integration
def test_store_upserts_questions_and_images_and_resolves_after_rerun(
    client: PostgresClient,
) -> None:
    quiz_question_repository = QuizQuestionStoreRepository("quiz_questions", client)
    quiz_image_repository = QuizImageStoreRepository("quiz_images", client)
    step = StoreQuizStep("store_quiz", quiz_question_repository, quiz_image_repository)
    context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [_image("abc.jpeg")],
        }
    )

    step.execute(context)

    question_rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert [row[0] for row in question_rows] == ["1"]

    image_rows = client.fetch(sql.SQL("SELECT filename FROM quiz_images"))
    assert [row[0] for row in image_rows] == ["abc.jpeg"]


@pytest.mark.integration
def test_store_removes_a_question_that_vanished_from_the_input(client: PostgresClient) -> None:
    quiz_question_repository = QuizQuestionStoreRepository("quiz_questions", client)
    quiz_image_repository = QuizImageStoreRepository("quiz_images", client)
    step = StoreQuizStep("store_quiz", quiz_question_repository, quiz_image_repository)
    first_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1"), _question("2")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
        }
    )
    step.execute(first_context)

    second_context = FlowContext(
        {
            context_keys.QUIZ_ENTITIES: [_question("1")],
            context_keys.QUIZ_IMAGE_ENTITIES: [],
        }
    )
    step.execute(second_context)

    rows = client.fetch(sql.SQL("SELECT number FROM quiz_questions"))
    assert [row[0] for row in rows] == ["1"]
