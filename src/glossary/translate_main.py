"""Fills glossary_entries.term_ru independently of build-glossary (FR-5).

`--dry-run` prints the step chain and exits: no filesystem write, no LLM call, no
database connection. `--force` retranslates every row, not only `term_ru IS NULL`.
"""

import argparse
import asyncio
import logging

from pywire import get_default_container

from commons.ai.observability import LlmCallTracker, ObservabilityConfig, build_llm_call_tracker
from commons.configs import OpenRouterConfig
from commons.observability import LOG_FORMAT, RunArtifactWriter
from glossary.configs import GlossaryConfig
from glossary.exceptions import GlossaryTranslationError
from glossary.models import GlossaryTermTranslationRequest
from glossary.services.glossary_term_translation_run_service import (
    GlossaryTermTranslationRunService,
)
from glossary.wiring import build_open_router_provider, build_postgres_client

logger = logging.getLogger(__name__)

_RUN_ID_PREFIX = "translate_glossary_terms"


def main() -> None:
    """Runs one `translate-glossary-terms` pass and prints its outcome."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Retranslate every row, not only term_ru IS NULL."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the step chain and exit; no I/O."
    )
    args = parser.parse_args()

    config = GlossaryConfig()  # pyright: ignore[reportCallIssue]

    if args.dry_run:
        selection = "every row" if args.force else "rows with term_ru IS NULL"
        print(
            "translate-glossary-terms --dry-run: no filesystem write, no LLM call, "
            f"no DB connection. Would select {selection}, batch by "
            f"{config.translation_batch_size}, translate, then UPDATE term_ru."
        )
        return

    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    provider = build_open_router_provider(
        OpenRouterConfig().api_key.get_secret_value()  # pyright: ignore[reportCallIssue]
    )
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

        service = container.resolve(GlossaryTermTranslationRunService)
        try:
            report = asyncio.run(service(GlossaryTermTranslationRequest(force=args.force)))
            print(f"Translated {report.translated} term(s); {report.still_missing} still missing.")
        except GlossaryTranslationError as error:
            print(f"FAILED: {error}")
            raise SystemExit(1) from error


if __name__ == "__main__":
    main()
