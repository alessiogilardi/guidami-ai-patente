from typing import Literal

from commons.clients import EmbeddingClient, VectorStoreClient
from commons.models.knowledge import KnowledgeChunk
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.entities import Article
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader


class IndexingPipeline:
    """Pipeline batch: legge il corpus, lo trasforma in chunk e ricostruisce il vector store."""

    def __init__(
        self,
        article_loader: ArticleLoader,
        article_chunker: ArticleChunker,
        embedding_client: EmbeddingClient,
        vector_store_client: VectorStoreClient,
        config: IngestorConfig,
    ) -> None:
        """Inietta le dipendenze della pipeline e la configurazione."""
        self._article_loader = article_loader
        self._article_chunker = article_chunker
        self._embedding_client = embedding_client
        self._vector_store_client = vector_store_client
        self._config = config

    def run(self) -> None:
        """Esegue il full reload di `knowledge_chunks` da CdS e CAP."""
        cds_articles = self._article_loader.load(self._config.cds_path)
        cap_articles = self._article_loader.load(self._config.cap_path)

        cds_chunks = self._chunk_articles(cds_articles, source="cds")
        cap_chunks = self._chunk_articles(cap_articles, source="cap")
        chunks = cds_chunks + cap_chunks

        self._assign_embeddings(chunks)

        self._vector_store_client.truncate()
        self._vector_store_client.bulk_insert(chunks)

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
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self._embedding_client.embed_passages(
                [chunk.chunk_text for chunk in batch]
            )
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.embedding = vector
