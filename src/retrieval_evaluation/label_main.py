"""Runs a golden-set labeling pass and persists it to the three golden-set tables.

For every quiz question with a query vector for the configured candidate variant,
builds the two-arm candidate union, asks `CommaLabelerAgent` which candidates justify
the correct answer, and writes the resulting labeling under one `labeling_runs` row
(spec 0011, phase 2). No `--dry-run`, no manifest, no `report.md` (AD-10): every real
invocation writes its own `logs/label_golden_set_<timestamp>/run.log`, same shape as
`retrieval_evaluation.main`.
"""

import argparse
import asyncio
import logging

from commons.observability import LOG_FORMAT, RunArtifactWriter
from domain.entities.evaluation import LabelingRunEntity
from guidami_ai_patente_ingestor.configs import IngestorConfig

from .services import CandidateSetService, GoldenSetLabelingService, QuestionLexemeService
from .utils import corpus_commit, prompt_version
from .wiring import (
    build_comma_labeler_agent,
    build_comma_labeler_config,
    build_corpus_repository,
    build_golden_set_repository,
    build_open_router_provider,
    build_postgres_client,
    build_quiz_repository,
    build_tracker,
)

logger = logging.getLogger(__name__)

_RUN_ID_PREFIX = "label_golden_set"


def main() -> None:
    """Runs one labeling pass over the quiz bank and prints its outcome breakdown."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="Maximum number of in-flight judge calls. Defaults to config.labeling.concurrency.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Shuffle seed for the presentation order. Defaults to config.labeling.shuffle_seed.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Restrict the run to this many questions, for a trial pass. Defaults to a full pass.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error(f"--limit must be >= 1, got {args.limit}")

    config = IngestorConfig.load()
    labeling = config.labeling
    seed = args.seed if args.seed is not None else labeling.shuffle_seed
    concurrency = args.concurrency if args.concurrency is not None else labeling.concurrency

    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    provider = build_open_router_provider(config)
    with (
        build_postgres_client(config) as postgres_client,
        build_tracker(postgres_client) as tracker,
    ):
        quiz_repository = build_quiz_repository(config, postgres_client)
        available_variants = quiz_repository.available_variants()
        if labeling.candidate_variant not in available_variants:
            parser.error(
                f"invalid candidate_variant {labeling.candidate_variant!r}, "
                f"must be one of {available_variants}"
            )

        corpus_repository = build_corpus_repository(config, postgres_client)
        golden_set_repository = build_golden_set_repository(config, postgres_client)
        agent_config = build_comma_labeler_config(config)
        agent = build_comma_labeler_agent(agent_config, provider, tracker)
        lexeme_service = QuestionLexemeService(labeling.lexeme_fields, corpus_repository)
        candidate_set_service = CandidateSetService(
            labeling.dense_k, labeling.text_k, corpus_repository, lexeme_service
        )
        service = GoldenSetLabelingService(
            candidate_variant=labeling.candidate_variant,
            shuffle_seed=seed,
            max_concurrency=concurrency,
            transport_retries=labeling.transport_retries,
            retry_backoff_seconds=labeling.retry_backoff_seconds,
            question_limit=args.limit,
            quiz_repository=quiz_repository,
            candidate_set_service=candidate_set_service,
            write_repository=golden_set_repository,
            agent=agent,
        )

        run_id = golden_set_repository.insert_run(
            LabelingRunEntity(
                judge_model=agent_config.model_name,
                prompt_version=prompt_version(agent_config.system, agent_config.user),
                candidate_variant=labeling.candidate_variant,
                dense_k=labeling.dense_k,
                text_k=labeling.text_k,
                shuffle_seed=seed,
                corpus_commit=corpus_commit(config.project_root),
                corpus_comma_count=corpus_repository.comma_count(),
                question_limit=args.limit,
            )
        )

        labeled = asyncio.run(service.label_all(run_id))

        with_commas, without_commas = golden_set_repository.outcome_counts(run_id)

    print(f"Run {run_id}: {labeled} domande etichettate.")
    print(f"  con almeno un comma: {with_commas} | senza alcun comma: {without_commas}")
    logger.info(
        "Run %d: %d domande etichettate (con almeno un comma: %d, senza alcun comma: %d)",
        run_id,
        labeled,
        with_commas,
        without_commas,
    )


if __name__ == "__main__":
    main()
