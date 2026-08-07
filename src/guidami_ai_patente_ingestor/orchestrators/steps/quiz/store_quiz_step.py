"""Persists QuizQuestionEntity/QuizImageEntity/QuizQuestionEmbeddingEntity records to the DB.

Upserts all three, plus reconciliation for questions.
"""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.quiz import QuizImageEntity, QuizQuestionEmbeddingEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.models.quiz import EmbedQuizVariantsResult
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import (
    QuizImageStoreRepository,
    QuizQuestionEmbeddingStoreRepository,
    QuizQuestionStoreRepository,
)

logger = logging.getLogger(__name__)


class StoreQuizStep(Step):
    """Persists quiz_questions, quiz_images, and quiz_question_embeddings to the DB.

    Domain-specific, mirroring StoreArticlesAndCommasStep: questions are upserted on
    `number` then reconciled against this run's own input — quiz has a single source, so
    reconciliation spans the whole table, unlike the knowledge side's per-source scope.
    Images are upserted on `filename` only; reconciling orphaned images is deferred (spec
    0008 Open Question). Variant rows (`quiz_question_embeddings`) are upserted on
    `(quiz_question_id, variant)`, resolving each row's `quiz_question_id` from the
    question's DB-generated id (only known after the question upsert returns it) — "one
    step, three tables" (FR-6).
    """

    def __init__(
        self,
        name: str,
        quiz_question_repository: QuizQuestionStoreRepository,
        quiz_image_repository: QuizImageStoreRepository,
        quiz_question_embedding_repository: QuizQuestionEmbeddingStoreRepository,
    ) -> None:
        """Injects the step name and the three store repositories."""
        super().__init__(name)
        self._quiz_question_repository = quiz_question_repository
        self._quiz_image_repository = quiz_image_repository
        self._quiz_question_embedding_repository = quiz_question_embedding_repository

    def execute(self, context: FlowContext) -> None:
        """Upserts questions (resolving ids) + images; reconciles questions against input.

        Upserts variant rows against the resolved question ids.
        """
        questions = cast(list[QuizQuestionEntity], context.get(context_keys.QUIZ_ENTITIES))
        images = cast(list[QuizImageEntity], context.get(context_keys.QUIZ_IMAGE_ENTITIES))
        embed_result = cast(
            EmbedQuizVariantsResult, context.get(context_keys.QUIZ_VARIANT_EMBEDDINGS)
        )

        logger.debug(
            "Upserting %d quiz questions, %d images, %d variant rows",
            len(questions),
            len(images),
            len(embed_result.variants),
        )

        question_ids = self._quiz_question_repository.upsert_returning_ids(questions)
        question_id_by_number = dict(
            zip((question.number for question in questions), question_ids, strict=True)
        )
        self._quiz_question_repository.delete_missing(questions)  # cascades to variant rows
        self._quiz_image_repository.upsert(images)

        embedding_entities = [
            QuizQuestionEmbeddingEntity(
                quiz_question_id=question_id_by_number[row.question_number],
                variant=row.variant,
                embedding_3_small=row.embedding,
            )
            for row in embed_result.variants
        ]
        self._quiz_question_embedding_repository.upsert(embedding_entities)

        logger.info(
            "Upserted %d quiz questions, %d images, %d variant rows (omissions: %s)",
            len(questions),
            len(images),
            len(embedding_entities),
            embed_result.omitted_counts,
        )

    def get_required_keys(self) -> set[str]:
        """Requires `QUIZ_ENTITIES`, `QUIZ_IMAGE_ENTITIES`, and `QUIZ_VARIANT_EMBEDDINGS`."""
        return {
            context_keys.QUIZ_ENTITIES,
            context_keys.QUIZ_IMAGE_ENTITIES,
            context_keys.QUIZ_VARIANT_EMBEDDINGS,
        }

    def get_produced_keys(self) -> set[str]:
        """No produced key: this is the flow's terminal (sink) step."""
        return set()
