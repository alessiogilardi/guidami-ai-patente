"""`ingest prepare` dispatch: clean + enrich flow pair, with idempotency check."""

import argparse
import logging

import psycopg
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.observability import LlmCallTracker
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

logger = logging.getLogger(__name__)

# Shared intermediate layer used by both preparation factory pairs.
_CLEANED_LAYER = "cleaned"


def dispatch_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
    tracker: LlmCallTracker | None,
) -> None:
    """Dispatch prepare subcommand: clean + enrich flow pair, with idempotency check."""
    force: bool = args.force
    match args.entity:
        case "knowledge":
            source: str = args.source
            clean_flow = build_knowledge_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
                source=source,
                force=force,
            )
            enrich_flow = build_knowledge_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                source=source,
                force=force,
                tracker=tracker,
            )
            # No run_preparation: per-element skipping lives in FilterAlreadyDoneStep
            # (Decision 11) — a per-element layer has no honest coarse skip signal.
            clean_flow.run()
            enrich_flow.run()
        case "quiz":
            quiz_source: str = config.quiz_preparation.sources[0]
            quiz_enrich_layer = config.quiz_preparation.output_layer
            if quiz_enrich_layer is None:
                raise ValueError("quiz_preparation.output_layer is not configured")
            clean_flow = build_quiz_cleaning_flow(
                config=config,
                layer_resolver=layer_resolver,
            )
            enrich_flow = build_quiz_enrichment_flow(
                config=config,
                layer_resolver=layer_resolver,
                open_router_provider=open_router_provider,
                tracker=tracker,
            )
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


def run_prepare(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    open_router_provider: OpenRouterProvider,
    args: argparse.Namespace,
) -> None:
    """Build the tracking DB client (best-effort) and dispatch the prepare subcommand.

    `PostgresClient` connects eagerly and `prepare` does not otherwise need a DB, so a
    connection/setup failure degrades gracefully: a warning is logged and the flows run
    untracked (`tracker=None`) instead of aborting the pipeline. `psycopg.Error` (not
    just `OperationalError`) is caught here: any failure while establishing the tracking
    connection is an observability concern, never a reason to abort `prepare`.
    """
    try:
        postgres_client = wiring.build_postgres_client(config)
    except psycopg.Error:
        logger.warning("Postgres unavailable; prepare will run without LLM call tracking")
        dispatch_prepare(config, layer_resolver, open_router_provider, args, tracker=None)
        return

    with postgres_client, wiring.build_tracker(postgres_client) as tracker:
        dispatch_prepare(config, layer_resolver, open_router_provider, args, tracker)
