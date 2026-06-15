import logging
import os

from commons.clients import E5SmallEmbeddingClient, VectorStoreClient
from commons.configs import VectorStoreConfig
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipelineBuilder
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleLoader

logger = logging.getLogger(__name__)


def main() -> None:
    """Esegue la pipeline di indicizzazione (full reload di `knowledge_chunks`)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    config = IngestorConfig(
        vector_store=VectorStoreConfig(database_url=os.environ["DATABASE_URL"])
    )
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
