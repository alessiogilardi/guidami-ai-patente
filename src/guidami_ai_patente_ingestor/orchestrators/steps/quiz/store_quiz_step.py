"""Persists QuizQuestionEntity/QuizImageEntity records to the DB.

Upserts both, plus reconciliation for questions.
"""

import logging
from typing import cast

from flowstep import FlowContext, Step

from domain.entities.quiz import QuizImageEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import (
    QuizImageStoreRepository,
    QuizQuestionStoreRepository,
)

logger = logging.getLogger(__name__)


class StoreQuizStep(Step):
    """Persists quiz_questions (upsert + reconciliation) and quiz_images (upsert) to the DB.

    Domain-specific, mirroring StoreArticlesAndCommasStep: questions are upserted on
    `number` then reconciled against this run's own input — quiz has a single source, so
    reconciliation spans the whole table, unlike the knowledge side's per-source scope.
    Images are upserted on `filename` only; reconciling orphaned images is deferred (spec
    0008 Open Question). Variant-row writing (`quiz_question_embeddings`) joins this step
    in spec 0008's next phase, which is why the step is named for the whole quiz write,
    not just today's two tables.
    """

    def __init__(
        self,
        name: str,
        quiz_question_repository: QuizQuestionStoreRepository,
        quiz_image_repository: QuizImageStoreRepository,
    ) -> None:
        """Injects the step name and the two store repositories."""
        super().__init__(name)
        self._quiz_question_repository = quiz_question_repository
        self._quiz_image_repository = quiz_image_repository

    def execute(self, context: FlowContext) -> None:
        """Upserts questions + images; reconciles questions against this run's input."""
        questions = cast(list[QuizQuestionEntity], context.get(context_keys.QUIZ_ENTITIES))
        images = cast(list[QuizImageEntity], context.get(context_keys.QUIZ_IMAGE_ENTITIES))

        logger.debug("Upserting %d quiz questions and %d quiz images", len(questions), len(images))

        self._quiz_question_repository.upsert(questions)
        self._quiz_question_repository.delete_missing(questions)
        self._quiz_image_repository.upsert(images)

        logger.info("Upserted %d quiz questions and %d quiz images", len(questions), len(images))

    def get_required_keys(self) -> set[str]:
        """Requires `QUIZ_ENTITIES` and `QUIZ_IMAGE_ENTITIES` as input."""
        return {context_keys.QUIZ_ENTITIES, context_keys.QUIZ_IMAGE_ENTITIES}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this is the flow's terminal (sink) step."""
        return set()
