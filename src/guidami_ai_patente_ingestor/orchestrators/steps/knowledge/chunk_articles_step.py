"""Step che trasforma gli articoli enriched in EmbeddableChunkModel (uno per comma)."""

import logging
from typing import Literal, cast

from flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticleModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

logger = logging.getLogger(__name__)


class ChunkArticlesStep(Step):
    """Chunka gli articoli della source corrente e produce la lista piatta di EmbeddableChunkModel.

    Nessun filtro repealed: i chunk repealed sono inclusi nell'output (il filtro
    è responsabilità di `EmbedChunksStep`). La `source` è iniettata: il flow è
    per-source (una run per source).
    """

    def __init__(
        self,
        name: str,
        source: Literal["cds", "cap"],
        article_chunker: ArticleChunker,
    ) -> None:
        """Inietta la source della run e il chunker di dominio.

        Args:
            name: Nome univoco dello step nel flow.
            source: Source degli articoli (es. "cds"), passata al chunker per ogni articolo.
            article_chunker: Servizio che trasforma un `EnrichedArticleModel` in
                `EmbeddableChunkModel`.
        """
        super().__init__(name)
        self._chunker = article_chunker
        self._source: Literal["cds", "cap"] = source

    def execute(self, context: FlowContext) -> None:
        """Legge `ENRICHED_ARTICLES`, chunka e scrive `EMBEDDABLE_CHUNKS` (lista piatta).

        Args:
            context: Shared pipeline context.
        """
        articles = cast(list[EnrichedArticleModel], context.get(context_keys.ENRICHED_ARTICLES))
        chunks = [chunk for article in articles for chunk in self._chunker(article)]

        logger.info(
            f"Chunked {len(articles)} articles for source '{self._source}' → {len(chunks)} chunks"
        )
        context.put(context_keys.EMBEDDABLE_CHUNKS, chunks)

    def get_required_keys(self) -> set[str]:
        """Richiede `ENRICHED_ARTICLES` in input."""
        return {context_keys.ENRICHED_ARTICLES}

    def get_produced_keys(self) -> set[str]:
        """Produce `EMBEDDABLE_CHUNKS`: lista piatta di EmbeddableChunkModel."""
        return {context_keys.EMBEDDABLE_CHUNKS}
