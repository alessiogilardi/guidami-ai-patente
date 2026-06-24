from typing import Protocol

from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


class QuizEnricher(Protocol):
    """Contratto uniforme di un passo di enrichment del quiz bank.

    Input e output sono lo stesso tipo (`EnrichedQuizModel`, ora flat): gli
    enricher sono componibili in catena, ognuno valorizza i propri campi
    lasciando intatti gli altri.
    """

    def enrich(self, questions: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Arricchisce le sotto-domande e ritorna nuovi modelli (non mutati in place).

        Args:
            questions: Sotto-domande enriched (flat) da arricchire ulteriormente.

        Returns:
            Nuove `EnrichedQuizModel` con i campi di competenza dell'enricher
            valorizzati.
        """
        ...
