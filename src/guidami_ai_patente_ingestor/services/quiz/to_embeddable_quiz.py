import logging

from commons.use_cases import UseCase
from commons.utils import deduplicate
from guidami_ai_patente_ingestor.mappers.quiz_mapper import QuizMapper
from guidami_ai_patente_ingestor.models.quiz.embeddable_quiz import EmbeddableQuizModel
from guidami_ai_patente_ingestor.models.quiz.enriched_quiz import EnrichedQuizModel

logger = logging.getLogger(__name__)


class ToEmbeddableQuiz(UseCase[list[EnrichedQuizModel], list[EmbeddableQuizModel]]):
    """Converte il quiz bank enriched (flat) in embeddable, con dedup.

    Un duplicato esatto è identificato dalla tripla (testo normalizzato,
    risposta corretta, identità immagine). Per ogni item mantenuto delega a
    `QuizMapper.from_enriched_to_embeddable`.
    """

    def execute(self, request: list[EnrichedQuizModel]) -> list[EmbeddableQuizModel]:
        """Dedup e mappa ogni item enriched in `EmbeddableQuizModel`.

        Args:
            request: Lista flat di domande enriched.

        Returns:
            Lista deduplicata di `EmbeddableQuizModel`.
        """
        return [
            QuizMapper.from_enriched_to_embeddable(item)
            for item in deduplicate(
                request,
                key=lambda item: (item.text.strip(), item.correct_answer, item.image),
                on_duplicate=lambda item: logger.warning(
                    "skipping duplicate quiz item %s", item.number
                ),
            )
        ]
