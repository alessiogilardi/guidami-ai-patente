"""Step che mappa il quiz bank enriched in EmbeddableQuizModel."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.mappers.quiz import QuizQuestionMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class MapToEmbeddableStep(Step):
    """Appiattisce e deduplica il quiz bank enriched in `EmbeddableQuizModel`.

    Delega a `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions`,
    che esegue la dedup (8 duplicati esatti → 7098 righe) prima dell'embedding.
    """

    def execute(self, context: FlowContext) -> None:
        """Legge `ENRICHED_QUIZ`, mappa e scrive `EMBEDDABLE_QUIZ`.

        Args:
            context: Shared pipeline context.
        """
        main_questions = cast(list[EnrichedQuizModel], context.get(context_keys.ENRICHED_QUIZ))
        embeddable = (
            QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions(
                main_questions
            )
        )
        logger.info(
            f"Mapped {len(main_questions)} main questions → {len(embeddable)} embeddable questions"
        )

        context.put(context_keys.EMBEDDABLE_QUIZ, embeddable)

    def get_required_keys(self) -> set[str]:
        """Richiede `ENRICHED_QUIZ` in input."""
        return {context_keys.ENRICHED_QUIZ}

    def get_produced_keys(self) -> set[str]:
        """Produce `EMBEDDABLE_QUIZ`: lista deduplicata di `EmbeddableQuizModel`."""
        return {context_keys.EMBEDDABLE_QUIZ}
