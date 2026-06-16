import logging

from commons.clients import LiteLLMEmbeddingClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators.quiz_indexing import QuizIndexingPipelineBuilder

logger = logging.getLogger(__name__)


def main() -> None:
    """Esegue la pipeline di indicizzazione del quiz bank."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]

    logger.info("starting quiz indexing pipeline")
    quiz_indexing_pipeline = (
        QuizIndexingPipelineBuilder(config)
        .with_embedding_client(LiteLLMEmbeddingClient(config.embedding))
        .build()
    )
    quiz_indexing_pipeline.run()
    logger.info("quiz indexing pipeline completed")
