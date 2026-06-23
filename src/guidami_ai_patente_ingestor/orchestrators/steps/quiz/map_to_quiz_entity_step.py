"""Step che mappa EmbeddableQuizModel nell'entità QuizQuestion."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.mappers.quiz import EmbeddableQuizQuestionMapper
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class MapToQuizEntityStep(Step):
    """Converte gli `EmbeddableQuizModel` embeddati nelle entità `QuizQuestion`.

    Delega a `EmbeddableQuizQuestionMapper.to_entity` per ogni item.
    """

    def execute(self, context: FlowContext) -> None:
        """Legge `EMBEDDABLE_QUIZ`, mappa e scrive `QUIZ_ENTITIES`.

        Args:
            context: Shared pipeline context.
        """
        embeddables = cast(list[EmbeddableQuizModel], context.get(context_keys.EMBEDDABLE_QUIZ))
        entities = [EmbeddableQuizQuestionMapper.to_entity(item) for item in embeddables]
        logger.info(f"Mapped {len(entities)} embeddable questions → quiz entities")

        context.put(context_keys.QUIZ_ENTITIES, entities)

    def get_required_keys(self) -> set[str]:
        """Richiede `EMBEDDABLE_QUIZ` in input."""
        return {context_keys.EMBEDDABLE_QUIZ}

    def get_produced_keys(self) -> set[str]:
        """Produce `QUIZ_ENTITIES`: lista di `QuizQuestion` pronte per lo store."""
        return {context_keys.QUIZ_ENTITIES}
