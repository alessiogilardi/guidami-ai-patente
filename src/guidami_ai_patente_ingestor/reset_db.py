import logging

from commons.clients import PostgresClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import KnowledgeChunkStoreRepository

logger = logging.getLogger(__name__)


def main() -> None:
    """Svuota la tabella `knowledge_chunks` in vista di un full reload."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]

    with PostgresClient(config.postgres) as client:
        KnowledgeChunkStoreRepository(client, config.knowledge_chunks_table).truncate()

    logger.info("knowledge_chunks table truncated")
