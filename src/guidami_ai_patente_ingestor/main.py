import logging

from commons.clients import E5SmallEmbeddingClient, VectorStoreClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.entities import article
from guidami_ai_patente_ingestor.orchestrators.knowledge_cleaning import CleaningPipelineBuilder
from guidami_ai_patente_ingestor.orchestrators.knowledge_indexing import IndexingPipelineBuilder
from guidami_ai_patente_ingestor.repositories import ArticleRepository, article_repository
from guidami_ai_patente_ingestor.services.knowledge import ArticleChunker, ArticleCleaner

logger = logging.getLogger(__name__)


def main() -> None:
    """Esegue la pipeline di pulizia (skip se già fatta) e di indicizzazione."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]

    article_repository = ArticleRepository()

    logger.info("starting cleaning pipeline")
    cleaning_pipeline = (
        CleaningPipelineBuilder(config)
        .with_article_repository(article_repository)
        .with_article_cleaner(ArticleCleaner())
        .build()
    )
    cleaning_pipeline.run()
    logger.info("cleaning pipeline completed")

    logger.info("starting indexing pipeline")
    indexing_pipeline = (
        IndexingPipelineBuilder(config)
        .with_article_repository(article_repository)
        .with_article_chunker(ArticleChunker())
        .with_embedding_client(E5SmallEmbeddingClient(config.embedding))
        .with_vector_store_client(VectorStoreClient(config.vector_store))
        .build()
    )
    indexing_pipeline.run()
    logger.info("indexing pipeline completed")
