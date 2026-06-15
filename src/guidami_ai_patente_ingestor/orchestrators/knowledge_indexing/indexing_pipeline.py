import logging
from typing import Literal

from commons.clients import EmbeddingClient
from commons.entities.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.repositories import (
    ArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

logger = logging.getLogger(__name__)


class IndexingPipeline:
    """Pipeline batch: legge il corpus, lo trasforma in chunk e ricostruisce il vector store."""

    def __init__(
        self,
        article_repository: ArticleRepository,
        article_chunker: ArticleChunker,
        embedding_client: EmbeddingClient,
        knowledge_chunk_store_repository: KnowledgeChunkStoreRepository,
        config: IngestorConfig,
    ) -> None:
        """Inietta le dipendenze della pipeline e la configurazione."""
        self._article_repository = article_repository
        self._article_chunker = article_chunker
        self._embedding_client = embedding_client
        self._knowledge_chunk_store_repository = knowledge_chunk_store_repository
        self._config = config

    def run(self) -> None:
        """Esegue il full reload di `knowledge_chunks` da CdS e CAP."""
        cds_articles = self._article_repository.load(self._config.cds_cleaned_path)
        cap_articles = self._article_repository.load(self._config.cap_cleaned_path)
        logger.info(f"loaded {len(cds_articles)} CdS articles, {len(cap_articles)} CAP articles")

        cds_chunks = self._chunk_articles(cds_articles, source="cds")
        cap_chunks = self._chunk_articles(cap_articles, source="cap")
        chunks = cds_chunks + cap_chunks
        logger.info(
            f"generated {len(cds_chunks)} CdS chunks, {len(cap_chunks)} CAP chunks "
            f"({len(chunks)} total)"
        )

        self._assign_embeddings(chunks)

        logger.info(f"truncating knowledge_chunks, inserting {len(chunks)} chunks")
        self._knowledge_chunk_store_repository.truncate()
        self._knowledge_chunk_store_repository.bulk_insert(chunks)
        logger.info("insertion completed")

    def _chunk_articles(
        self, articles: list[Article], source: Literal["cds", "cap"]
    ) -> list[KnowledgeChunk]:
        return [
            chunk
            for article in articles
            for chunk in self._article_chunker.chunk(article, source)
        ]

    def _assign_embeddings(self, chunks: list[KnowledgeChunk]) -> None:
        batch_size = self._config.embedding_batch_size
        total_batches = -(-len(chunks) // batch_size)  # ceil division
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            batch_number = start // batch_size + 1
            logger.info(f"embedding batch {batch_number}/{total_batches} ({len(batch)} chunks)")
            vectors = self._embedding_client.embed_passages(
                [chunk.chunk_text for chunk in batch]
            )
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
