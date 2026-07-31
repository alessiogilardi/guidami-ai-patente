"""`ingest prepare` dispatch: clean + enrich flow pair, with idempotency check."""

import argparse
import logging

import psycopg
from pydantic_ai.providers.openrouter import OpenRouterProvider
from rich.console import Console

from commons.ai.observability import LlmCallTracker
from commons.observability import ProgressReporter
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.orchestrators import (
    build_knowledge_cleaning_flow,
    build_knowledge_enrichment_flow,
    build_quiz_cleaning_flow,
    build_quiz_enrichment_flow,
    run_preparation,
)
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)

# Shared intermediate layer used by both preparation factory pairs.
_CLEANED_LAYER = "cleaned"


def _render_prepare_dry_run(args: argparse.Namespace) -> None:
    """Describes the flow pair `dispatch_prepare` would run, without building any of it."""
    force: bool = args.force
    console = Console()
    match args.entity:
        case "knowledge":
            source: str = args.source
            steps = [
                f"knowledge_cleaning ({source}): LoadJsonStep(parsed/{source}) -> "
                f"clean + stamp source -> FilterAlreadyDoneStep(force={force}) -> "
                f"WriteJsonDirStep(cleaned/{source})",
                f"knowledge_enrichment ({source}): LoadJsonDirStep(cleaned/{source}) -> "
                f"FilterAlreadyDoneStep(force={force}) -> map -> "
                "LLM enrich (ArticleContextualizerAgent) -> "
                f"WriteJsonDirStep(enriched/{source})",
            ]
            render_dry_run(console, f"prepare {args.entity}", steps)
        case "quiz":
            skip_note = f"(skipped entirely if already present, force={force})"
            steps = [
                f"quiz_cleaning: LoadJsonStep(parsed/quiz) -> flatten + dedup -> "
                f"WriteJsonStep(cleaned/quiz) {skip_note}",
                "quiz_enrichment: LoadJsonStep(cleaned/quiz) -> map -> "
                "LLM enrich (RoadSignDescriberAgent, NormReferenceDescriberAgent) -> "
                f"WriteJsonStep(enriched/quiz) {skip_note}",
            ]
            render_dry_run(console, f"prepare {args.entity}", steps)


def dispatch_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
    tracker: LlmCallTracker | None,
    progress: ProgressReporter,
) -> None:
    """Dispatch prepare subcommand: clean + enrich flow pair, with idempotency check."""
    force: bool = args.force
    progress.begin_run(2)
    match args.entity:
        case "knowledge":
            source: str = args.source
            clean_flow = build_knowledge_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                source=source,
                force=force,
                progress=progress,
            )
            enrich_flow = build_knowledge_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                source=source,
                force=force,
                tracker=tracker,
                progress=progress,
            )
            # No run_preparation: per-element skipping lives in FilterAlreadyDoneStep
            # (Decision 11) — a per-element layer has no honest coarse skip signal.
            progress.begin_flow("knowledge_cleaning")
            clean_flow.run()
            progress.end_flow()
            progress.begin_flow("knowledge_enrichment")
            enrich_flow.run()
            progress.end_flow()
        case "quiz":
            quiz_source: str = config.quiz_preparation.sources[0]
            quiz_enrich_layer = config.quiz_preparation.output_layer
            if quiz_enrich_layer is None:
                raise ValueError("quiz_preparation.output_layer is not configured")
            clean_flow = build_quiz_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                progress=progress,
            )
            enrich_flow = build_quiz_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                tracker=tracker,
                progress=progress,
            )
            progress.begin_flow("quiz_cleaning")
            run_preparation(
                clean_flow,
                layer_resolver.path(_CLEANED_LAYER, quiz_source),
                force=force,
            )
            progress.end_flow()
            progress.begin_flow("quiz_enrichment")
            run_preparation(
                enrich_flow,
                layer_resolver.path(quiz_enrich_layer, quiz_source),
                force=force,
            )
            progress.end_flow()


def run_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
    progress: ProgressReporter,
) -> None:
    """Build the tracking DB client (best-effort) and dispatch the prepare subcommand.

    `PostgresClient` connects eagerly and `prepare` does not otherwise need a DB, so a
    connection/setup failure degrades gracefully: a warning is logged and the flows run
    untracked (`tracker=None`) instead of aborting the pipeline. `psycopg.Error` (not
    just `OperationalError`) is caught here: any failure while establishing the tracking
    connection is an observability concern, never a reason to abort `prepare`.
    """
    if args.dry_run:
        _render_prepare_dry_run(args)
        return

    try:
        postgres_client = wiring.build_postgres_client(config)
    except psycopg.Error:
        logger.warning("Postgres unavailable; prepare will run without LLM call tracking")
        dispatch_prepare(
            config, layer_resolver, open_router_provider, args, tracker=None, progress=progress
        )
        return

    with postgres_client, wiring.build_tracker(postgres_client) as tracker:
        dispatch_prepare(
            config, layer_resolver, open_router_provider, args, tracker, progress=progress
        )
