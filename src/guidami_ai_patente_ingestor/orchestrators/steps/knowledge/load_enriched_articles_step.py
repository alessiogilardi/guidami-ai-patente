"""Step che carica gli articoli enriched da disco per tutte le source configurate."""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.repositories import EnrichedArticleRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadEnrichedArticlesStep(Step):
    """Carica gli articoli enriched da disco per tutte le source e li espone nel context.

    Produce `ARTICLES_BY_SOURCE`: un dict `{source: list[EnrichedArticle]}`.
    Non richiede chiavi in input: è il primo step del flow di indexing.
    """

    def __init__(
        self,
        name: str,
        enriched_article_repository: EnrichedArticleRepository,
        layer_resolver: LayerResolver,
        input_layer: str,
        sources: list[str],
    ) -> None:
        """Inietta il repository, il resolver e i selettori di layer/source.

        Args:
            name: Nome univoco dello step nel flow.
            enriched_article_repository: Repository per la lettura degli articoli enriched da JSON.
            layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
            input_layer: Nome del layer di input (es. "enriched").
            sources: Lista delle chiavi source da caricare (es. ["cds", "cap"]).
        """
        super().__init__(name)
        self._repository = enriched_article_repository
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._sources = sources

    def execute(self, context: FlowContext) -> None:
        """Carica gli articoli per ogni source e scrive il dict in `ARTICLES_BY_SOURCE`.

        Args:
            context: Shared pipeline context.
        """
        articles_by_source: dict[str, list[EnrichedArticle]] = {}
        for source in self._sources:
            path = self._layer_resolver.path(self._input_layer, source)
            articles = self._repository.load(path)
            articles_by_source[source] = cast(list[EnrichedArticle], articles)
            logger.info(f"Loaded {len(articles)} enriched articles for source '{source}'")

        context.put(context_keys.ARTICLES_BY_SOURCE, articles_by_source)

    def get_required_keys(self) -> set[str]:
        """Nessuna chiave richiesta: questo step è il punto di partenza del flow."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produce `ARTICLES_BY_SOURCE`: dict per-source degli articoli caricati."""
        return {context_keys.ARTICLES_BY_SOURCE}
