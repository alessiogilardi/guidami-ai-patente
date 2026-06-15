import logging

from commons.clients import VectorStoreClient
from guidami_ai_patente_ingestor.configs import IngestorConfig

logger = logging.getLogger(__name__)


def main() -> None:
    """Svuota la tabella `knowledge_chunks` in vista di un full reload."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]

    with VectorStoreClient(config.vector_store) as client:
        client.truncate()

    logger.info("knowledge_chunks table truncated")
