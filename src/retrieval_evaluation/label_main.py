"""Runs a golden-set labeling pass and persists it to the three golden-set tables.

For every quiz question with a query vector for the configured candidate variant,
builds the two-arm candidate union, asks `CommaLabelerAgent` which candidates justify
the correct answer, and writes the resulting labeling under one `labeling_runs` row
(spec 0011, phase 2). No `--dry-run`, no manifest, no `report.md` (AD-10): every real
invocation writes its own `logs/label_golden_set_<timestamp>/run.log`, same shape as
`retrieval_evaluation.main`.

`--topic` (repeatable) restricts the run to the union of the named topics, applied
before `--limit` (FR-18). It is a selection criterion only — it never reaches
`labeling_runs` and plays no part in the judge's configuration epoch.
"""

import argparse
import asyncio
import logging

from commons.ai.observability import ObservabilityConfig, build_llm_call_tracker
from commons.observability import LOG_FORMAT, RunArtifactWriter
from domain.enums import LabelingRunOrigin
from guidami_ai_patente_ingestor.configs import IngestorConfig
from labeling.mappers import LabelingEpochMapper, LabelingRunMapper
from labeling.services import GoldenSetLabelingService
from labeling.utils import corpus_commit
from labeling.wiring import (
    build_candidate_set_service,
    build_comma_labeler_agent,
    build_comma_labeler_config,
    build_corpus_repository,
    build_golden_set_repository,
    build_open_router_provider,
    build_postgres_client,
    build_question_labeling_service,
    build_question_lexeme_service,
    build_quiz_repository,
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
    parser.add_argument(
        "--topic",
        action="append",
        default=None,
        metavar="TOPIC",
        help=(
            "Restrict the run to this topic; repeatable, and the union is labeled. "
            "Omit for the full bank. Selects which questions are labeled, never how "
            "they are judged: it is not recorded on the run."
        ),
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error(f"--limit must be >= 1, got {args.limit}")

    config = IngestorConfig.load()
    observability_config = ObservabilityConfig.load()
    labeling = config.labeling
    seed = args.seed if args.seed is not None else labeling.shuffle_seed
    concurrency = args.concurrency if args.concurrency is not None else labeling.concurrency

    run_dir = RunArtifactWriter.build_run_dir(config.project_root / "logs", _RUN_ID_PREFIX)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.getLogger().addHandler(file_handler)

    # D7/D14: `QuestionLabelingService` crosses `asyncio.to_thread` for its
    # Postgres-touching calls (candidate set, labeling insert), so up to
    # `concurrency` workers borrow a connection simultaneously — no longer the
    # implicit serialisation of the pre-extraction code path. `+ 1` budgets for
    # QueuedLlmCallTracker's own background borrow alongside them.
    postgres_config = config.postgres.model_copy(
        update={"pool_max_size": max(config.postgres.pool_max_size, concurrency + 1)}
    )

    provider = build_open_router_provider(config.open_router_config.api_key.get_secret_value())
    with (
        build_postgres_client(postgres_config) as postgres_client,
        build_llm_call_tracker(observability_config, postgres_client) as tracker,
    ):
        quiz_repository = build_quiz_repository(
            config.quiz_questions_table,
            config.quiz_question_embeddings_table,
            config.quiz_images_table,
            postgres_client,
        )
        available_variants = quiz_repository.available_variants()
        if labeling.candidate_variant not in available_variants:
            parser.error(
                f"invalid candidate_variant {labeling.candidate_variant!r}, "
                f"must be one of {available_variants}"
            )

        corpus_repository = build_corpus_repository(
            config.articles_table, config.article_commas_table, postgres_client
        )
        golden_set_repository = build_golden_set_repository(
            config.labeling_runs_table,
            config.quiz_labelings_table,
            config.quiz_comma_labels_table,
            postgres_client,
        )
        agent_config = build_comma_labeler_config(labeling.agents_dir)
        agent = build_comma_labeler_agent(agent_config, provider, tracker)
        lexeme_service = build_question_lexeme_service(labeling, corpus_repository)
        candidate_set_service = build_candidate_set_service(
            labeling, corpus_repository, lexeme_service
        )
        question_labeling_service = build_question_labeling_service(
            labeling, seed, candidate_set_service, golden_set_repository, agent
        )
        service = GoldenSetLabelingService(
            candidate_variant=labeling.candidate_variant,
            shuffle_seed=seed,
            max_concurrency=concurrency,
            question_limit=args.limit,
            topics=args.topic,
            quiz_repository=quiz_repository,
            question_labeling_service=question_labeling_service,
        )

        epoch = LabelingEpochMapper.from_config_to_epoch(labeling, agent_config)
        run_id = golden_set_repository.insert_run(
            LabelingRunMapper.from_epoch_to_entity(
                epoch,
                LabelingRunOrigin.BATCH,
                shuffle_seed=seed,
                corpus_comma_count=corpus_repository.comma_count(),
                corpus_commit=corpus_commit(config.project_root),
                question_limit=args.limit,
            )
        )

        labeled = asyncio.run(service(run_id))

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
