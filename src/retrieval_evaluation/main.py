"""Samples quiz questions and judges their retrieved commas for clarity.

Asks an LLM judge whether each question's top-k retrieved commas clearly and
unambiguously justify its correct answer, either over a random sample (`--n`,
the default) or over the whole quiz bank (`--all`). Exploratory measurement,
deliberately outside the `ingest evaluate retrieval` harness (spec 0007): no
manifest, no run artifacts, no dry-run chain. Re-run with `--n` a few times to
gauge judge stability, then once with `--all` (or a larger `--n`) for a final
estimate.
"""

import argparse
import logging
import random

from guidami_ai_patente_ingestor.configs import IngestorConfig

from .models import RetrievalJudgeItemResult
from .services import RetrievalJudgeEvaluationService
from .wiring import (
    build_agent,
    build_corpus_repository,
    build_open_router_provider,
    build_postgres_client,
    build_quiz_repository,
    build_tracker,
)

logger = logging.getLogger(__name__)

_DEFAULT_N = 10
_DEFAULT_K = 10


def _report(results: list[RetrievalJudgeItemResult]) -> None:
    for result in results:
        verdict = "CHIARO" if result.is_clear else "NON CHIARO"
        print(f"[{verdict}] quiz {result.quiz_number}: {result.rationale}")

    share_clear = sum(1 for result in results if result.is_clear) / len(results)
    print(f"\n{len(results)} quiz giudicati, {share_clear:.1%} chiari.")


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
    args = parser.parse_args()

    config = IngestorConfig.load()
    provider = build_open_router_provider(config)
    with (
        build_postgres_client(config) as postgres_client,
        build_tracker(postgres_client) as tracker,
    ):
        agent = build_agent(config, provider, tracker)
        service = RetrievalJudgeEvaluationService(
            k=args.k,
            variant=config.evaluation.quiz_embedding_variant,
            quiz_repository=build_quiz_repository(config, postgres_client),
            corpus_repository=build_corpus_repository(config, postgres_client),
            agent=agent,
        )
        results = (
            service.evaluate_all()
            if args.all
            else service.evaluate(n=args.n, rng=random.Random(args.seed))
        )

    _report(results)


if __name__ == "__main__":
    main()
