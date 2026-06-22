"""Step che carica il quiz bank enriched da disco per la source quiz."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizMainQuestion
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import EnrichedQuizBankRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadEnrichedQuizStep(Step):
    """Carica il quiz bank enriched da disco e lo espone nel context.

    Produce `ENRICHED_QUIZ`, una lista di `EnrichedQuizMainQuestion`. Non
    richiede chiavi in input: è il primo step del flow di quiz indexing.
    """

    def __init__(
        self,
        name: str,
        enriched_quiz_bank_repository: EnrichedQuizBankRepository,
        layer_resolver: LayerResolver,
        input_layer: str,
        source: str,
    ) -> None:
        """Inietta il repository, il resolver e i selettori di layer/source.

        Args:
            name: Nome univoco dello step nel flow.
            enriched_quiz_bank_repository: Repository di lettura del quiz bank enriched da JSON.
            layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
            input_layer: Nome del layer di input (es. "enriched").
            source: Chiave della source da caricare (es. "quiz").
        """
        super().__init__(name)
        self._repository = enriched_quiz_bank_repository
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Carica il quiz bank della source e scrive la lista in `ENRICHED_QUIZ`.

        Args:
            context: Shared pipeline context.
        """
        path = self._layer_resolver.path(self._input_layer, self._source)
        questions = cast(list[EnrichedQuizMainQuestion], self._repository.load(path))
        logger.info(
            f"Loaded {len(questions)} enriched quiz main questions for source '{self._source}'"
        )

        context.put(context_keys.ENRICHED_QUIZ, questions)

    def get_required_keys(self) -> set[str]:
        """Nessuna chiave richiesta: questo step è il punto di partenza del flow."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produce `ENRICHED_QUIZ`: lista delle domande madri enriched della source."""
        return {context_keys.ENRICHED_QUIZ}
