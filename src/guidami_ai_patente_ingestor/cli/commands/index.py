"""`ingest index` dispatch: build the indexing flow for the target entity and run it."""

import argparse
import logging
from typing import cast

from rich.console import Console

from commons.ai.embedding import LiteLLMEmbeddingClient
from commons.observability import ProgressReporter
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.models.quiz import EmbedQuizVariantsResult
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_indexing_flow,
    build_quiz_indexing_flow,
    context_keys,
)
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring
from ..models.run_artifacts import IndexManifest
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)


def _render_index_dry_run(args: argparse.Namespace) -> None:
    """Describes the indexing flow that would run, without building any of it."""
    console = Console()
    match args.entity:
        case "knowledge":
            source: str = args.source
            steps = [
                f"knowledge_indexing ({source}): LoadJsonDirStep(cleaned/{source}) -> "
                "map_to_article_entities -> expand_to_embeddable_commas -> embed_commas -> "
                f"store_articles_and_commas (tables=articles,article_commas, "
                f"source={source}, full source reload)",
            ]
            render_dry_run(console, f"index {args.entity}", steps)
        case "quiz":
            steps = [
                "quiz_indexing: LoadJsonStep(enriched/quiz) -> map_to_embedded (dedup) -> "
                "embed_quiz_variants -> map_to_quiz_entity -> map_to_quiz_images -> "
                "store_quiz (tables=quiz_questions,quiz_question_embeddings,quiz_images, "
                "upsert + reconciliation)",
            ]
            render_dry_run(console, f"index {args.entity}", steps)


def run_index(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    args: argparse.Namespace,
    manifest: IndexManifest | None,
    progress: ProgressReporter,
) -> None:
    """Dispatch index subcommand: build indexing flow and run it."""
    if args.dry_run:
        _render_index_dry_run(args)
        return

    assert manifest is not None

    embedding_client = LiteLLMEmbeddingClient(config.embedding)
    postgres_client = wiring.build_postgres_client(config)
    progress.begin_run(1)
    match args.entity:
        case "knowledge":
            source: str = args.source
            flow = build_knowledge_indexing_flow(
                config=config,
                layer_resolver=layer_resolver,
                embedding_client=embedding_client,
                postgres_client=postgres_client,
                source=source,
                progress=progress,
            )
            logger.info(f"starting knowledge indexing for source '{source}'")
            manifest.record_flow("knowledge_indexing")
            progress.begin_flow("knowledge_indexing")
            flow.run()
            progress.end_flow()
            logger.info(f"knowledge indexing completed for source '{source}'")
        case "quiz":
            flow = build_quiz_indexing_flow(
                config=config,
                layer_resolver=layer_resolver,
                embedding_client=embedding_client,
                postgres_client=postgres_client,
                progress=progress,
            )
            logger.info("starting quiz indexing")
            manifest.record_flow("quiz_indexing")
            progress.begin_flow("quiz_indexing")
            result_context = flow.run()
            progress.end_flow()
            embed_result = cast(
                EmbedQuizVariantsResult, result_context.get(context_keys.QUIZ_VARIANT_EMBEDDINGS)
            )
            manifest.record_quiz_variant_omissions(embed_result.omitted_counts)
            logger.info("quiz variant omissions: %s", embed_result.omitted_counts)
            logger.info("quiz indexing completed")
