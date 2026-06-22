"""Entrypoint CLI per `ingest-knowledge` — indicizza il corpus per una source."""

import argparse
import logging

from commons.clients import LiteLLMEmbeddingClient, PostgresClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import build_knowledge_indexing_flow
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


def main() -> None:
    """Esegue il flow di knowledge indexing per-source (corpus → chunk → embed → store)."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Indicizza il corpus normativo per una source.")
    parser.add_argument(
        "--source",
        required=True,
        help="Source da indicizzare (es. 'cds', 'cap').",
    )
    args = parser.parse_args()

    # pyright non sa che i campi richiesti sono popolati da env/.env/YAML a runtime.
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)

    flow = build_knowledge_indexing_flow(
        config=config,
        layer_resolver=layer_resolver,
        embedding_client=LiteLLMEmbeddingClient(config.embedding),
        postgres_client=PostgresClient(config.postgres),
        source=args.source,
    )

    logger.info(f"starting knowledge indexing flow for source '{args.source}'")
    flow.run()
    logger.info(f"knowledge indexing flow completed for source '{args.source}'")
