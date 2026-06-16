from typing import Self

from commons.clients import EmbeddingClient, PostgresClient, SentenceTransformerEmbeddingClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    ArticleRepository,
    KnowledgeChunkStoreRepository,
)
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker

from .indexing_pipeline import IndexingPipeline


class IndexingPipelineBuilder:
    """Valida `IngestorConfig` e assembla `IndexingPipeline` con le dipendenze concrete.

    Le dipendenze concrete possono essere sovrascritte tramite i metodi `with_*`
    (fluent), ad es. per iniettare fake/mock nei test senza toccare i moduli interni.
    """

    def __init__(self, config: IngestorConfig) -> None:
        """Memorizza la configurazione da cui costruire la pipeline."""
        self._config = config
        self._article_repository: ArticleRepository | None = None
        self._article_chunker: ArticleChunker | None = None
        self._embedding_client: EmbeddingClient | None = None
        self._knowledge_chunk_store_repository: KnowledgeChunkStoreRepository | None = None

    def with_article_repository(self, article_repository: ArticleRepository) -> Self:
        """Sostituisce l'`ArticleRepository` di default."""
        self._article_repository = article_repository
        return self

    def with_article_chunker(self, article_chunker: ArticleChunker) -> Self:
        """Sostituisce l'`ArticleChunker` di default."""
        self._article_chunker = article_chunker
        return self

    def with_embedding_client(self, embedding_client: EmbeddingClient) -> Self:
        """Sostituisce l'`EmbeddingClient` di default (`SentenceTransformerEmbeddingClient`)."""
        self._embedding_client = embedding_client
        return self

    def with_knowledge_chunk_store_repository(
        self, knowledge_chunk_store_repository: KnowledgeChunkStoreRepository
    ) -> Self:
        """Sostituisce il `KnowledgeChunkStoreRepository` di default."""
        self._knowledge_chunk_store_repository = knowledge_chunk_store_repository
        return self

    def build(self) -> IndexingPipeline:
        """Verifica i path sorgente e assembla la pipeline."""
        self._validate_source_paths()
        return IndexingPipeline(
            article_repository=(
                self._article_repository
                if self._article_repository is not None
                else ArticleRepository()
            ),
            article_chunker=(
                self._article_chunker
                if self._article_chunker is not None
                else ArticleChunker()
            ),
            embedding_client=(
                self._embedding_client
                if self._embedding_client is not None
                else SentenceTransformerEmbeddingClient(self._config.embedding)
            ),
            knowledge_chunk_store_repository=(
                self._knowledge_chunk_store_repository
                if self._knowledge_chunk_store_repository is not None
                else KnowledgeChunkStoreRepository(
                    PostgresClient(self._config.postgres), self._config.knowledge_chunks_table
                )
            ),
            config=self._config,
        )

    def _validate_source_paths(self) -> None:
        missing = [
            path
            for path in (self._config.cds_cleaned_path, self._config.cap_cleaned_path)
            if not path.exists()
        ]
        if missing:
            paths = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"File sorgente non trovato: {paths}")
