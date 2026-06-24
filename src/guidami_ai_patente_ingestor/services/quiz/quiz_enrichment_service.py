from guidami_ai_patente_ingestor.mappers.quiz import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel, QuizBankModel

from .enrichers import QuizEnricher


class QuizEnrichmentService:
    """Base-map del quiz bank seguito dall'applicazione in catena degli enricher."""

    def __init__(self, enrichers: list[QuizEnricher]) -> None:
        """Inietta gli enricher da applicare, in ordine.

        Args:
            enrichers: Lista ordinata di enricher; lista vuota → solo base-map.
        """
        self._enrichers = enrichers

    def enrich(self, questions: list[QuizBankModel]) -> list[EnrichedQuizModel]:
        """Mappa il quiz bank sorgente in enriched e applica gli enricher in ordine.

        Args:
            questions: Domande madri sorgente da arricchire.

        Returns:
            `EnrichedQuizModel` risultanti dal base-map e dalla catena di enricher.
        """
        enriched = [QuizMapper.from_quiz_bank_to_enriched(question) for question in questions]
        for enricher in self._enrichers:
            enriched = enricher.enrich(enriched)
        return enriched
