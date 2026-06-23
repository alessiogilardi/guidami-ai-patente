"""Step che scrive gli articoli cleaned su disco per una singola source."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class WriteCleanedStep(Step):
    """Scrive gli articoli cleaned su disco per UNA source.

    Sink terminale del flow di clean: legge `CLEANED_ARTICLES` e li persiste
    sul layer "cleaned" via `ArticleRepository.write`.
    """

    def __init__(
        self,
        name: str,
        article_repository: ArticleRepository,
        layer_resolver: LayerResolver,
        output_layer: str,
        source: str,
    ) -> None:
        """Inietta il repository, il resolver e i selettori di layer/source.

        Args:
            name: Nome univoco dello step nel flow.
            article_repository: Repository per la scrittura degli articoli cleaned su JSON.
            layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
            output_layer: Nome del layer di output (costante "cleaned").
            source: Chiave della source da scrivere (es. "cds").
        """
        super().__init__(name)
        self._repository = article_repository
        self._layer_resolver = layer_resolver
        self._output_layer = output_layer
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Legge `CLEANED_ARTICLES` e scrive gli articoli sul path risolto.

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[Article], context.get(context_keys.CLEANED_ARTICLES))
        path = self._layer_resolver.path(self._output_layer, self._source)
        self._repository.write(articles, path)

        logger.info(f"Wrote {len(articles)} cleaned articles for source '{self._source}'")

    def get_required_keys(self) -> set[str]:
        """Richiede `CLEANED_ARTICLES` in input."""
        return {context_keys.CLEANED_ARTICLES}

    def get_produced_keys(self) -> set[str]:
        """Nessuna chiave prodotta: questo step è il punto di arrivo del flow."""
        return set()
