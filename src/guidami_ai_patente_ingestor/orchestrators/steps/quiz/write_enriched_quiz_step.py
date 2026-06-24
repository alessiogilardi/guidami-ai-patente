"""Step che scrive il quiz bank enriched su disco per la source quiz."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import EnrichedQuizBankRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class WriteEnrichedQuizStep(Step):
    """Scrive il quiz bank enriched su disco per la source quiz.

    Sink terminale del flow di quiz preparation: legge `ENRICHED_QUIZ` e lo
    persiste sul layer di output via `EnrichedQuizBankRepository.write`.
    """

    def __init__(
        self,
        name: str,
        enriched_quiz_bank_repository: EnrichedQuizBankRepository,
        layer_resolver: LayerResolver,
        output_layer: str,
        source: str,
    ) -> None:
        """Inietta il repository, il resolver e i selettori di layer/source.

        Args:
            name: Nome univoco dello step nel flow.
            enriched_quiz_bank_repository: Repository per la scrittura del quiz bank
                enriched su JSON.
            layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
            output_layer: Nome del layer di output (es. "enriched").
            source: Chiave della source da scrivere (es. "quiz").
        """
        super().__init__(name)
        self._repository = enriched_quiz_bank_repository
        self._layer_resolver = layer_resolver
        self._output_layer = output_layer
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Legge `ENRICHED_QUIZ` e scrive le domande sul path risolto.

        Args:
            context: Shared pipeline context.
        """
        questions = cast(list[EnrichedQuizModel], context.get(context_keys.ENRICHED_QUIZ))
        path = self._layer_resolver.path(self._output_layer, self._source)
        self._repository.write(questions, path)

        logger.info(
            f"Wrote {len(questions)} enriched quiz main questions for source '{self._source}'"
        )

    def get_required_keys(self) -> set[str]:
        """Richiede `ENRICHED_QUIZ` in input."""
        return {context_keys.ENRICHED_QUIZ}

    def get_produced_keys(self) -> set[str]:
        """Nessuna chiave prodotta: questo step è il punto di arrivo del flow."""
        return set()
