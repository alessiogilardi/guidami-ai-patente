"""`ingest index` dispatch: build the indexing flow for the target entity and run it."""

import argparse
import logging

from commons.ai.embedding import LiteLLMEmbeddingClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_indexing_flow,
    build_quiz_indexing_flow,
)
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring

logger = logging.getLogger(__name__)


def run_index(
    config: IngestorConfig, layer_resolver: LayerResolver, args: argparse.Namespace
) -> None:
    """Dispatch index subcommand: build indexing flow and run it."""
    embedding_client = LiteLLMEmbeddingClient(config.embedding)
    postgres_client = wiring.build_postgres_client(config)
    match args.entity:
        case "knowledge":
            source: str = args.source
            flow = build_knowledge_indexing_flow(
                config=config,
                layer_resolver=layer_resolver,
                embedding_client=embedding_client,
                postgres_client=postgres_client,
                source=source,
            )
            logger.info(f"starting knowledge indexing for source '{source}'")
            flow.run()
            logger.info(f"knowledge indexing completed for source '{source}'")
        case "quiz":
            flow = build_quiz_indexing_flow(
                config=config,
                layer_resolver=layer_resolver,
                embedding_client=embedding_client,
                postgres_client=postgres_client,
            )
            logger.info("starting quiz indexing")
            flow.run()
            logger.info("quiz indexing completed")
