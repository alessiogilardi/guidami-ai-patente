"""Builds the glossary_entries table, block by block, never translating (FR-2).

`--dry-run` prints the blocks and the step chain that would run and exits: no
filesystem write, no LLM call, no database connection. `--force` rebuilds every
configured block, even one that already has entries.
"""

import argparse
import asyncio
import logging

from pywire import get_default_container

from commons.ai.observability import LlmCallTracker, ObservabilityConfig, build_llm_call_tracker
from commons.observability import LOG_FORMAT, RunArtifactWriter
from glossary.configs import GlossaryConfig
from glossary.exceptions import GlossaryBuildError
from glossary.models import GlossaryBuildRequest
from glossary.services.glossary_build_service import GlossaryBuildService
from glossary.wiring import (
    build_embedding_service,
    build_open_router_provider,
    build_postgres_client,
)

logger = logging.getLogger(__name__)

_RUN_ID_PREFIX = "build_glossary"


def main() -> None:
    """Runs one `build-glossary` pass and prints its per-block outcome."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Rebuild every configured block.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the step chain and exit; no I/O."
    )
    args = parser.parse_args()

    config = GlossaryConfig()  # pyright: ignore[reportCallIssue]

    if args.dry_run:
        print("build-glossary --dry-run: no filesystem write, no LLM call, no DB connection.")
        for block in config.blocks:
            comma = block.comma_number or "all"
            print(
                f"  would process {block.source}/{block.article_number}/{comma}: "
                f"read -> extract -> embed -> upsert -> reconcile"
                + (" (skip unless --force)" if not args.force else " (forced)")
            )
        return

    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    open_router_config_key = _load_open_router_api_key()
    provider = build_open_router_provider(open_router_config_key)
    observability_config = ObservabilityConfig.load()

    with (
        build_postgres_client(config.postgres) as postgres_client,
        build_llm_call_tracker(observability_config, postgres_client) as tracker,
    ):
        container = get_default_container()
        container.register_instance(config, as_type=GlossaryConfig)
        container.register_instance(postgres_client, as_type=type(postgres_client))
        container.register_instance(provider, as_type=type(provider))
        container.register_instance(tracker, as_type=LlmCallTracker)
        embedding_service = build_embedding_service(config.embedding_batch_size)
        container.register_instance(embedding_service, as_type=type(embedding_service))

        service = container.resolve(GlossaryBuildService)
        try:
            report = asyncio.run(service(GlossaryBuildRequest(force=args.force)))
            _print_outcomes(report.outcomes)
        except GlossaryBuildError as error:
            _print_outcomes(error.outcomes)
            print(f"FAILED: {error}")
            raise SystemExit(1) from error


def _load_open_router_api_key() -> str:
    from commons.configs import OpenRouterConfig

    return OpenRouterConfig().api_key.get_secret_value()  # pyright: ignore[reportCallIssue]


def _print_outcomes(outcomes) -> None:  # noqa: ANN001
    for outcome in outcomes:
        status = "skipped" if outcome.skipped else f"{outcome.entries_written} entries written"
        print(f"  {outcome.label}: {status}")


if __name__ == "__main__":
    main()
