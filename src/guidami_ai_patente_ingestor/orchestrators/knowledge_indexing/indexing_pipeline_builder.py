from commons.clients import E5SmallEmbeddingClient, VectorStoreClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader

from .indexing_pipeline import IndexingPipeline


class IndexingPipelineBuilder:
    """Valida `IngestorConfig` e assembla `IndexingPipeline` con le dipendenze concrete."""

    def __init__(self, config: IngestorConfig) -> None:
        """Memorizza la configurazione da cui costruire la pipeline."""
        self._config = config

    def build(self) -> IndexingPipeline:
        """Verifica i path sorgente e assembla la pipeline."""
        self._validate_source_paths()
        return IndexingPipeline(
            article_loader=ArticleLoader(),
            article_chunker=ArticleChunker(),
            embedding_client=E5SmallEmbeddingClient(self._config.embedding),
            vector_store_client=VectorStoreClient(self._config.vector_store),
            config=self._config,
        )

    def _validate_source_paths(self) -> None:
        for path in (self._config.cds_path, self._config.cap_path):
            if not path.exists():
                raise FileNotFoundError(f"File sorgente non trovato: {path}")
