"""Step che carica gli articoli parsed da disco per una singola source."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import ArticleRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadParsedArticlesStep(Step):
    """Carica gli articoli parsed da disco per UNA source e li espone nel context.

    La preparation è per-source (una run per source): produce `PARSED_ARTICLES`,
    una lista piatta di `Article`. Non richiede chiavi in input: è il primo
    step del flow di clean.
    """

    def __init__(
        self,
        name: str,
        article_repository: ArticleRepository,
        layer_resolver: LayerResolver,
        input_layer: str,
        source: str,
    ) -> None:
        """Inietta il repository, il resolver e i selettori di layer/source.

        Args:
            name: Nome univoco dello step nel flow.
            article_repository: Repository per la lettura degli articoli parsed da JSON.
            layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
            input_layer: Nome del layer di input (es. "parsed").
            source: Chiave della source da caricare (es. "cds").
        """
        super().__init__(name)
        self._repository = article_repository
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._source = source

    def execute(self, context: FlowContext) -> None:
        """Carica gli articoli della source e scrive la lista in `PARSED_ARTICLES`.

        Args:
            context: Shared pipeline context.
        """
        path = self._layer_resolver.path(self._input_layer, self._source)
        articles = cast(list[Article], self._repository.load(path))
        logger.info(f"Loaded {len(articles)} parsed articles for source '{self._source}'")

        context.put(context_keys.PARSED_ARTICLES, articles)

    def get_required_keys(self) -> set[str]:
        """Nessuna chiave richiesta: questo step è il punto di partenza del flow."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produce `PARSED_ARTICLES`: lista piatta degli articoli della source."""
        return {context_keys.PARSED_ARTICLES}
