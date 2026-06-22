"""Step che trasforma gli articoli enriched in KnowledgeChunk (uno per comma)."""

import logging
from typing import Literal, cast

from commons.entities.knowledge import KnowledgeChunk
from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.models.knowledge import EnrichedArticle
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

logger = logging.getLogger(__name__)

_KNOWN_SOURCES: frozenset[str] = frozenset({"cds", "cap"})


class ChunkArticlesStep(Step):
    """Chunka tutti gli articoli di ogni source e produce la lista piatta di KnowledgeChunk.

    Nessun filtro repealed: i chunk repealed sono inclusi nell'output (il filtro
    è responsabilità di `EmbedChunksStep`).
    """

    def __init__(self, name: str, article_chunker: ArticleChunker) -> None:
        """Inietta il chunker di dominio.

        Args:
            name: Nome univoco dello step nel flow.
            article_chunker: Servizio che trasforma un `EnrichedArticle` in `KnowledgeChunk`.
        """
        super().__init__(name)
        self._chunker = article_chunker

    def execute(self, context: FlowContext) -> None:
        """Legge `ARTICLES_BY_SOURCE`, chunka e scrive `CHUNKS` (lista piatta).

        Args:
            context: Shared pipeline context.
        """
        articles_by_source = cast(
            dict[str, list[EnrichedArticle]], context.get(context_keys.ARTICLES_BY_SOURCE)
        )
        chunks: list[KnowledgeChunk] = []
        for source, articles in articles_by_source.items():
            typed_source = cast(Literal["cds", "cap"], source)
            source_chunks = [
                chunk
                for article in articles
                for chunk in self._chunker.chunk(article, typed_source)
            ]
            chunks.extend(source_chunks)
            logger.info(
                f"Chunked {len(articles)} articles for source '{source}' "
                f"→ {len(source_chunks)} chunks"
            )

        logger.info(f"Total chunks produced: {len(chunks)}")
        context.put(context_keys.CHUNKS, chunks)

    def get_required_keys(self) -> set[str]:
        """Richiede `ARTICLES_BY_SOURCE` in input."""
        return {context_keys.ARTICLES_BY_SOURCE}

    def get_produced_keys(self) -> set[str]:
        """Produce `CHUNKS`: lista piatta di KnowledgeChunk."""
        return {context_keys.CHUNKS}
