"""Step che mappa il quiz bank enriched in EmbeddableQuizModel.

NOTE (SP09 plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md):
`EnrichedQuizModel` è ora flat (nessun `sub_questions`), quindi questo step
(indexing, fuori scope per SP09) non è più semanticamente corretto e fallisce
il type-check su `sub_questions`. Rottura nota e accettata, non riparata qui
(vedi sezione "Out of scope" del piano) — il fix è tracciato in un piano
futuro di adeguamento dell'indexing.
"""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.mappers.quiz import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel, EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys

logger = logging.getLogger(__name__)


class MapToEmbeddableStep(Step):
    """Appiattisce e deduplica il quiz bank enriched in `EmbeddableQuizModel`.

    Un duplicato esatto è identificato dalla tripla (testo normalizzato,
    risposta corretta, identità immagine). Per ogni item mantenuto delega a
    `QuizMapper.from_enriched_quiz_item_to_embeddable`.
    """

    def execute(self, context: FlowContext) -> None:
        """Legge `ENRICHED_QUIZ`, appiattisce+dedup e scrive `EMBEDDABLE_QUIZ`.

        Args:
            context: Shared pipeline context.
        """
        main_questions = cast(list[EnrichedQuizModel], context.get(context_keys.ENRICHED_QUIZ))
        embeddable = self._flatten_and_dedup(main_questions)
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

    @staticmethod
    def _flatten_and_dedup(
        main_questions: list[EnrichedQuizModel],
    ) -> list[EmbeddableQuizModel]:
        embeddable: list[EmbeddableQuizModel] = []
        seen: set[tuple[str, bool, str | None]] = set()

        for main_question in main_questions:
            for sub_question in main_question.sub_questions:  # pyright: ignore[reportAttributeAccessIssue]
                text = sub_question.text.strip()
                key = (text, sub_question.correct_answer, sub_question.image)
                if key in seen:
                    logger.warning(
                        f"skipping duplicate sub-question {sub_question.number} "
                        f"(question_id={main_question.question_id})"
                    )
                    continue
                seen.add(key)
                embeddable.append(
                    QuizMapper.from_enriched_quiz_item_to_embeddable(sub_question, main_question)
                )

        return embeddable
