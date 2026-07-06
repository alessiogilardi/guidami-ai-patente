"""Unified CLI entry point for `ingest` (SP07).

Subcommand structure:
    ingest prepare knowledge --source <cds|cap> [--force]
    ingest prepare quiz [--force]
    ingest index knowledge --source <cds|cap>
    ingest index quiz
    ingest reset knowledge
    ingest reset quiz
"""

import argparse
import logging

from commons.clients import LiteLLMEmbeddingClient, PostgresClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_cleaning_flow,
    build_knowledge_enrichment_flow,
    build_knowledge_indexing_flow,
    build_quiz_cleaning_flow,
    build_quiz_enrichment_flow,
    build_quiz_indexing_flow,
    run_preparation,
)
from guidami_ai_patente_ingestor.repositories import (
    KnowledgeChunkStoreRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)

# Shared intermediate layer used by both preparation factory pairs.
_CLEANED_LAYER = "cleaned"


def _build_parser(config: IngestorConfig) -> argparse.ArgumentParser:
    """Build the nested-subcommand argument parser from config-driven source catalogs."""
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Unified ingestion CLI for guidami-ai-patente.",
    )
    cmd_subs = parser.add_subparsers(dest="command", required=True)

    # ---- prepare ----
    prepare_p = cmd_subs.add_parser("prepare", help="Run preparation flows.")
    prep_subs = prepare_p.add_subparsers(dest="entity", required=True)

    prep_k = prep_subs.add_parser("knowledge", help="Prepare knowledge corpus.")
    prep_k.add_argument(
        "--source",
        required=True,
        choices=config.knowledge_preparation.sources,
        help="Source to prepare (e.g. 'cds', 'cap').",
    )
    prep_k.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run even if output already exists.",
    )

    prep_q = prep_subs.add_parser("quiz", help="Prepare quiz bank.")
    prep_q.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-run even if output already exists.",
    )

    # ---- index ----
    index_p = cmd_subs.add_parser("index", help="Run indexing flows.")
    idx_subs = index_p.add_subparsers(dest="entity", required=True)

    idx_k = idx_subs.add_parser("knowledge", help="Index knowledge corpus.")
    idx_k.add_argument(
        "--source",
        required=True,
        choices=config.knowledge_indexing.sources,
        help="Source to index (e.g. 'cds', 'cap').",
    )

    idx_subs.add_parser("quiz", help="Index quiz bank.")

    # ---- reset ----
    reset_p = cmd_subs.add_parser("reset", help="Truncate DB tables (full wipe).")
    rst_subs = reset_p.add_subparsers(dest="entity", required=True)
    rst_subs.add_parser("knowledge", help="Truncate knowledge_chunks table.")
    rst_subs.add_parser("quiz", help="Truncate quiz_questions table.")

    return parser


def _run_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    args: argparse.Namespace,
) -> None:
    """Dispatch prepare subcommand: clean + enrich flow pair, with idempotency check."""
    force: bool = args.force
    match args.entity:
        case "knowledge":
            source: str = args.source
            knowledge_enrich_layer = config.knowledge_preparation.output_layer
            if knowledge_enrich_layer is None:
                raise ValueError("knowledge_preparation.output_layer is not configured")
            clean_flow = build_knowledge_cleaning_flow(
                config=config, layer_resolver=layer_resolver, source=source
            )
            enrich_flow = build_knowledge_enrichment_flow(
                config=config, layer_resolver=layer_resolver, source=source
            )
            run_preparation(
                clean_flow,
                layer_resolver.path(_CLEANED_LAYER, source),
                force=force,
            )
            run_preparation(
                enrich_flow,
                layer_resolver.path(knowledge_enrich_layer, source),
                force=force,
            )
        case "quiz":
            quiz_source: str = config.quiz_preparation.sources[0]
            quiz_enrich_layer = config.quiz_preparation.output_layer
            if quiz_enrich_layer is None:
                raise ValueError("quiz_preparation.output_layer is not configured")
            clean_flow = build_quiz_cleaning_flow(config=config, layer_resolver=layer_resolver)
            enrich_flow = build_quiz_enrichment_flow(config=config, layer_resolver=layer_resolver)
            run_preparation(
                clean_flow,
                layer_resolver.path(_CLEANED_LAYER, quiz_source),
                force=force,
            )
            run_preparation(
                enrich_flow,
                layer_resolver.path(quiz_enrich_layer, quiz_source),
                force=force,
            )


def _run_index(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    args: argparse.Namespace,
) -> None:
    """Dispatch index subcommand: build indexing flow and run it."""
    embedding_client = LiteLLMEmbeddingClient(config.embedding)
    postgres_client = PostgresClient(config.postgres)
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


def _run_reset(config: IngestorConfig, args: argparse.Namespace) -> None:
    """Dispatch reset subcommand: truncate the target DB table (full wipe)."""
    postgres_client = PostgresClient(config.postgres)
    match args.entity:
        case "knowledge":
            KnowledgeChunkStoreRepository(
                config.knowledge_chunks_table, postgres_client
            ).truncate()
            logger.info("knowledge_chunks table truncated")
        case "quiz":
            QuizQuestionStoreRepository(config.quiz_questions_table, postgres_client).truncate()
            logger.info("quiz_questions table truncated")


def main() -> None:
    """Entry point: `ingest <command> <entity> [options]`."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = IngestorConfig()  # pyright: ignore[reportCallIssue]
    layer_resolver = LayerResolver(layers=config.layers, sources=config.sources)

    parser = _build_parser(config)
    args = parser.parse_args()

    match args.command:
        case "prepare":
            _run_prepare(config, layer_resolver, args)
        case "index":
            _run_index(config, layer_resolver, args)
        case "reset":
            _run_reset(config, args)
