"""`ingest index` dispatch: build the indexing flow for the target entity and run it."""

import argparse
import logging

from rich.console import Console

from commons.ai.embedding import LiteLLMEmbeddingClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_indexing_flow,
    build_quiz_indexing_flow,
)
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)


def _render_index_dry_run(args: argparse.Namespace) -> None:
    """Describes the indexing flow that would run, without building any of it."""
    console = Console()
    match args.entity:
        case "knowledge":
            source: str = args.source
            steps = [
                f"knowledge_indexing ({source}): LoadJsonDirStep(enriched/{source}) -> "
                "chunk_articles -> embed_chunks -> map_to_chunk_entity -> "
                f"store_chunks (table=knowledge_chunks, source={source}, full source reload)",
            ]
            render_dry_run(console, f"index {args.entity}", steps)
        case "quiz":
            steps = [
                "quiz_indexing: LoadJsonStep(enriched/quiz) -> map_to_embedded (dedup) -> "
                "embed_quiz -> map_to_quiz_entity -> "
                "store_quiz (table=quiz_questions, full table reload)",
            ]
            render_dry_run(console, f"index {args.entity}", steps)


def run_index(
    config: IngestorConfig, layer_resolver: LayerResolver, args: argparse.Namespace
) -> None:
    """Dispatch index subcommand: build indexing flow and run it."""
    if args.dry_run:
        _render_index_dry_run(args)
        return

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
