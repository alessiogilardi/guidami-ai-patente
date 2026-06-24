"""Step che arricchisce il quiz bank delegando a QuizEnrichmentService."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.quiz import QuizBankModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.services import QuizEnrichmentService

logger = logging.getLogger(__name__)


class EnrichQuizStep(Step):
    """Arricchisce il quiz bank delegando l'intera logica a `QuizEnrichmentService`.

    Resta sottile: legge `CLEANED_QUIZ`, delega al service, scrive `ENRICHED_QUIZ`.
    """

    def __init__(self, name: str, quiz_enrichment_service: QuizEnrichmentService) -> None:
        """Inietta il service di enrichment.

        Args:
            name: Nome univoco dello step nel flow.
            quiz_enrichment_service: Service che esegue base-map + catena di enricher.
        """
        super().__init__(name)
        self._service = quiz_enrichment_service

    def execute(self, context: FlowContext) -> None:
        """Legge `CLEANED_QUIZ`, arricchisce e scrive `ENRICHED_QUIZ`.

        Args:
            context: Shared pipeline context.
        """
        questions = cast(list[QuizBankModel], context.get(context_keys.CLEANED_QUIZ))
        enriched = self._service.enrich(questions)
        logger.info(f"Enriched {len(enriched)} quiz main questions")

        context.put(context_keys.ENRICHED_QUIZ, enriched)

    def get_required_keys(self) -> set[str]:
        """Richiede `CLEANED_QUIZ` in input."""
        return {context_keys.CLEANED_QUIZ}

    def get_produced_keys(self) -> set[str]:
        """Produce `ENRICHED_QUIZ`."""
        return {context_keys.ENRICHED_QUIZ}
