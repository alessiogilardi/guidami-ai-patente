"""Samples quiz questions and judges their retrieved commas for clarity.

Asks an LLM judge whether each question's top-k retrieved commas clearly and
unambiguously justify its correct answer, either over a random sample (`--n`,
the default) or over the whole quiz bank (`--all`). Exploratory measurement,
deliberately outside the `ingest evaluate retrieval` harness (spec 0007): no
manifest, no report.md, no dry-run chain. Every run still writes its own
`logs/evaluate_judge_<timestamp>/run.log` and `results.json` (full per-question
judged records), so a batch can be inspected after the fact instead of only
via the console printout. Re-run with `--n` a few times to gauge judge
stability, then once with `--all` (or a larger `--n`) for a final estimate.
"""

import argparse
import asyncio
import json
import logging
import random
from pathlib import Path

from commons.ai.observability import ObservabilityConfig, build_llm_call_tracker
from commons.observability import LOG_FORMAT, RunArtifactWriter
from guidami_ai_patente_ingestor.configs import IngestorConfig

from .models import RetrievalJudgeItemResult
from .services import RetrievalJudgeEvaluationService
from .wiring import (
    build_agent,
    build_corpus_repository,
    build_open_router_provider,
    build_postgres_client,
    build_quiz_repository,
)

logger = logging.getLogger(__name__)

_DEFAULT_N = 10
_DEFAULT_K = 10
_DEFAULT_CONCURRENCY = 8
_RUN_ID_PREFIX = "evaluate_judge"


def _report(results: list[RetrievalJudgeItemResult]) -> None:
    for result in results:
        verdict = "CHIARO" if result.is_clear else "NON CHIARO"
        image_suffix = ""
        if result.image_filename:
            image_suffix = f" [img: {result.image_filename}] {result.image_description}"
        print(f"[{verdict}] quiz {result.quiz_number}: {result.rationale}{image_suffix}")

    share_clear = sum(1 for result in results if result.is_clear) / len(results)
    print(f"\n{len(results)} quiz giudicati, {share_clear:.1%} chiari.")


def _write_results(run_dir: Path, results: list[RetrievalJudgeItemResult]) -> None:
    """Writes the full judged records (quiz, retrieved commas, verdict) to `results.json`."""
    results_file = run_dir / "results.json"
    payload = [result.model_dump(mode="json") for result in results]
    results_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote %d judged result(s) to %s", len(results), results_file)


def main() -> None:
    """Runs one judged pass (`--n` sample, or `--all`) and prints the verdicts."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n", type=int, default=_DEFAULT_N, help="Number of quiz questions to sample."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Judge every quiz question instead of sampling --n.",
    )
    parser.add_argument(
        "--k", type=int, default=_DEFAULT_K, help="Number of commas retrieved per question."
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed, for a reproducible sample."
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        help="Quiz embedding variant to evaluate. Defaults to "
        "config.evaluation.quiz_embedding_variant.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_CONCURRENCY,
        help="Maximum number of in-flight judge calls.",
    )
    args = parser.parse_args()

    config = IngestorConfig.load()
    observability_config = ObservabilityConfig.load()

    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    provider = build_open_router_provider(config)
    with (
        build_postgres_client(config) as postgres_client,
        build_llm_call_tracker(observability_config, postgres_client) as tracker,
    ):
        quiz_repository = build_quiz_repository(config, postgres_client)
        variant = args.variant or config.evaluation.quiz_embedding_variant
        available_variants = quiz_repository.available_variants()
        if variant not in available_variants:
            parser.error(f"invalid --variant {variant!r}, must be one of {available_variants}")

        agent = build_agent(config, provider, tracker)
        service = RetrievalJudgeEvaluationService(
            k=args.k,
            variant=variant,
            max_concurrency=args.concurrency,
            quiz_repository=quiz_repository,
            corpus_repository=build_corpus_repository(config, postgres_client),
            agent=agent,
        )
        results = asyncio.run(
            service.evaluate_all()
            if args.all
            else service.evaluate(n=args.n, rng=random.Random(args.seed))
        )

    _report(results)
    _write_results(run_dir, results)


if __name__ == "__main__":
    main()
