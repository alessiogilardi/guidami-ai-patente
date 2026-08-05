"""`ingest prepare` dispatch: knowledge cleaning, quiz clean + enrich pair."""

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
    build_quiz_cleaning_flow,
    build_quiz_enrichment_flow,
)
from guidami_ai_patente_ingestor.services import LayerResolver

from .. import wiring
from ..models.run_artifacts import PrepareManifest
from ..rendering import render_dry_run

logger = logging.getLogger(__name__)


def _render_prepare_dry_run(args: argparse.Namespace) -> None:
    """Describes the flow(s) `dispatch_prepare` would run, without building any of them."""
    force: bool = args.force
    console = Console()
    match args.entity:
        case "knowledge":
            source: str = args.source
            steps = [
                f"knowledge_cleaning ({source}): LoadJsonStep(parsed/{source}) -> "
                f"clean + stamp source -> FilterAlreadyDoneStep(force={force}) -> "
                f"WriteJsonDirStep(cleaned/{source})",
            ]
            render_dry_run(console, f"prepare {args.entity}", steps)
        case "quiz":
            steps = [
                "quiz_cleaning: LoadJsonStep(parsed/quiz) -> flatten + dedup -> "
                f"FilterAlreadyDoneStep(force={force}) -> WriteJsonDirStep(cleaned/quiz)",
                "quiz_enrichment: LoadJsonDirStep(cleaned/quiz) -> "
                f"FilterAlreadyDoneStep(force={force}) -> map -> "
                "LLM enrich (RoadSignDescriberAgent, NormReferenceDescriberAgent) -> "
                "WriteJsonDirStep(enriched/quiz)",
            ]
            render_dry_run(console, f"prepare {args.entity}", steps)


def dispatch_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
    tracker: LlmCallTracker | None,
    manifest: PrepareManifest,
    progress: ProgressReporter,
) -> None:
    """Dispatch prepare subcommand: knowledge cleaning only, quiz clean + enrich pair."""
    force: bool = args.force
    match args.entity:
        case "knowledge":
            source: str = args.source
            # One flow now (FR-16/AD-18, T-13): context enrichment has been removed.
            progress.begin_run(1)
            clean_flow = build_knowledge_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                source=source,
                force=force,
                progress=progress,
            )
            # No run_preparation: per-element skipping lives in FilterAlreadyDoneStep
            # (Decision 11) — a per-element layer has no honest coarse skip signal.
            manifest.record_flow("knowledge_cleaning")
            progress.begin_flow("knowledge_cleaning")
            clean_flow.run()
            progress.end_flow()
        case "quiz":
            progress.begin_run(2)
            clean_flow = build_quiz_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                force=force,
                progress=progress,
            )
            enrich_flow = build_quiz_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                force=force,
                tracker=tracker,
                progress=progress,
            )
            # No run_preparation: per-element skipping lives in FilterAlreadyDoneStep,
            # mirroring the knowledge branch.
            manifest.record_flow("quiz_cleaning")
            progress.begin_flow("quiz_cleaning")
            clean_flow.run()
            progress.end_flow()
            manifest.record_flow("quiz_enrichment")
            progress.begin_flow("quiz_enrichment")
            enrich_flow.run()
            progress.end_flow()


def run_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
    manifest: PrepareManifest | None,
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

    assert manifest is not None

    try:
        postgres_client = wiring.build_postgres_client(config)
    except psycopg.Error:
        logger.warning("Postgres unavailable; prepare will run without LLM call tracking")
        dispatch_prepare(
            config,
            layer_resolver,
            open_router_provider,
            args,
            tracker=None,
            manifest=manifest,
            progress=progress,
        )
        return

    with postgres_client, wiring.build_tracker(postgres_client) as tracker:
        dispatch_prepare(
            config,
            layer_resolver,
            open_router_provider,
            args,
            tracker,
            manifest=manifest,
            progress=progress,
        )
