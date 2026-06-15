import logging

from commons.clients import E5SmallEmbeddingClient, VectorStoreClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipelineBuilder
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader

logger = logging.getLogger(__name__)


def main() -> None:
    """Esegue la pipeline di indicizzazione (full reload di `knowledge_chunks`)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    logger.info("starting indexing pipeline")
    pipeline = (
        IndexingPipelineBuilder(config)
        .with_article_loader(ArticleLoader())
        .with_article_chunker(ArticleChunker())
        .with_embedding_client(E5SmallEmbeddingClient(config.embedding))
        .with_vector_store_client(VectorStoreClient(config.vector_store))
        .build()
    )
    pipeline.run()
    logger.info("indexing pipeline completed")
