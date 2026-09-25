"""Fills glossary_entries.definition_plain independently of build-glossary (spec 0022 FR-2).

`--dry-run` prints the step chain and exits: no filesystem write, no LLM call, no
database connection. `--force` resimplifies every row, not only
`definition_plain IS NULL`.
"""

import argparse
import asyncio
import logging

from openai import AsyncOpenAI
from pydantic_ai.providers import Provider
from pywire import get_default_container

from commons.ai.observability import LlmCallTracker, ObservabilityConfig, build_llm_call_tracker
from commons.configs import OpenRouterConfig
from commons.observability import LOG_FORMAT, RunArtifactWriter
from glossary.configs import GlossaryConfig
from glossary.exceptions import GlossaryDefinitionSimplificationError
from glossary.models import GlossaryDefinitionSimplificationRequest
from glossary.services.glossary_definition_simplification_run_service import (
    GlossaryDefinitionSimplificationRunService,
)
from glossary.wiring import build_open_router_provider, build_postgres_client

logger = logging.getLogger(__name__)

_RUN_ID_PREFIX = "simplify_glossary_definitions"


def main() -> None:
    """Runs one `simplify-glossary-definitions` pass and prints its outcome."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Resimplify every row, not only definition_plain IS NULL.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the step chain and exit; no I/O."
    )
    args = parser.parse_args()

    config = GlossaryConfig()  # pyright: ignore[reportCallIssue]

    if args.dry_run:
        selection = "every row" if args.force else "rows with definition_plain IS NULL"
        print(
            "simplify-glossary-definitions --dry-run: no filesystem write, no LLM call, "
            f"no DB connection. Would select {selection}, batch by "
            f"{config.simplification_batch_size}, simplify, then UPDATE definition_plain."
        )
        return

    _setup_logging(config)

    provider = build_open_router_provider(OpenRouterConfig())  # pyright: ignore[reportCallIssue]
    observability_config = ObservabilityConfig.load()

    with (
        build_postgres_client(config.postgres) as postgres_client,
        build_llm_call_tracker(observability_config, postgres_client) as tracker,
    ):
        container = get_default_container()
        container.register_instance(config, as_type=GlossaryConfig)
        container.register_instance(postgres_client, as_type=type(postgres_client))
        container.register_instance(provider, as_type=Provider[AsyncOpenAI])
        container.register_instance(tracker, as_type=LlmCallTracker)

        service = container.resolve(GlossaryDefinitionSimplificationRunService)
        try:
            report = asyncio.run(
                service(GlossaryDefinitionSimplificationRequest(force=args.force))
            )
            print(
                f"Simplified {report.simplified} definition(s); "
                f"{report.still_missing} still missing."
            )
        except GlossaryDefinitionSimplificationError as error:
            print(f"FAILED: {error}")
            raise SystemExit(1) from error


def _setup_logging(config: GlossaryConfig) -> None:
    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)


if __name__ == "__main__":
    main()
