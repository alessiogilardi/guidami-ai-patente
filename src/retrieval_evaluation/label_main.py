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

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import LlmCallLogRepository, QueuedLlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.observability import LOG_FORMAT, RunArtifactWriter
from commons.repositories import YamlRepository
from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from domain.entities.evaluation import LabelingRunEntity
from guidami_ai_patente_ingestor.configs import IngestorConfig
from labeling.agents import CommaLabelerAgent
from labeling.repositories import GoldenSetWriteRepository
from labeling.services import CandidateSetService, GoldenSetLabelingService, QuestionLexemeService
from labeling.utils import corpus_commit, prompt_version

logger = logging.getLogger(__name__)

_RUN_ID_PREFIX = "label_golden_set"


# The following builders are deliberately duplicated in `main.py` (spec 0012, Task 5):
# they used to be shared through `retrieval_evaluation/wiring.py`, but that module is
# now trimmed to `build_retrieval_judge_agent` only. Task 6 reparameterises them (off
# plain values instead of `IngestorConfig`) and extracts the reparameterised versions
# into a shared `labeling.wiring`, at which point this duplication goes away.
def _build_open_router_provider(config: IngestorConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.open_router_config.api_key.get_secret_value())


def _build_postgres_client(config: IngestorConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config.postgres)


def _build_tracker(postgres_client: PostgresClient) -> QueuedLlmCallTracker:
    """Builds the queued LLM call tracker, persisted through the given client."""
    return QueuedLlmCallTracker(LlmCallLogRepository(postgres_client))


def _build_quiz_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> QuizReadRepository:
    """Builds the quiz read repository, reusing the ingestor's table names."""
    return QuizReadRepository(
        config.quiz_questions_table,
        config.quiz_question_embeddings_table,
        config.quiz_images_table,
        postgres_client,
    )


def _build_corpus_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> CorpusReadRepository:
    """Builds the corpus read repository, reusing the ingestor's table names."""
    return CorpusReadRepository(
        config.articles_table, config.article_commas_table, postgres_client
    )


def _build_golden_set_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> GoldenSetWriteRepository:
    """Builds the golden-set write repository, reusing the ingestor's table names."""
    return GoldenSetWriteRepository(
        config.labeling_runs_table,
        config.quiz_labelings_table,
        config.quiz_comma_labels_table,
        postgres_client,
    )


def _build_comma_labeler_config(config: IngestorConfig) -> AgentConfig:
    """Loads `comma_labeler.yaml` from the shared labeling config's `agents_dir`.

    This is the judge: its prompt hash **is** the configuration epoch (AD-22), so it
    reads `agents_dir` from `LabelingConfig`, not from `IngestorConfig` directly.
    """
    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.labeling.agents_dir)
    )
    return agents_repository.load_one("comma_labeler.yaml")


def _build_comma_labeler_agent(
    agent_config: AgentConfig,
    provider: OpenRouterProvider,
    tracker: QueuedLlmCallTracker,
) -> CommaLabelerAgent:
    """Builds the comma-labeler agent from an already-loaded `AgentConfig`.

    Takes the config already loaded (rather than calling `from_yaml`) so the entry
    point loads the prompt exactly once and both hashes it (AD-11) and builds the
    agent from it.
    """
    return CommaLabelerAgent(config=agent_config, provider=provider, tracker=tracker)


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

    provider = _build_open_router_provider(config)
    with (
        _build_postgres_client(config) as postgres_client,
        _build_tracker(postgres_client) as tracker,
    ):
        quiz_repository = _build_quiz_repository(config, postgres_client)
        available_variants = quiz_repository.available_variants()
        if labeling.candidate_variant not in available_variants:
            parser.error(
                f"invalid candidate_variant {labeling.candidate_variant!r}, "
                f"must be one of {available_variants}"
            )

        corpus_repository = _build_corpus_repository(config, postgres_client)
        golden_set_repository = _build_golden_set_repository(config, postgres_client)
        agent_config = _build_comma_labeler_config(config)
        agent = _build_comma_labeler_agent(agent_config, provider, tracker)
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
                # Stopgap (spec 0012, D9): the sanctioned constructor for this entity
                # is LabelingEpochMapper (Task 4), which does not exist yet. Sorting
                # here mirrors the rule it will encapsulate. `origin` needs no explicit
                # value: LabelingRunOrigin.BATCH is the entity's default and this run
                # is a batch run.
                lexeme_fields=tuple(sorted(field.value for field in labeling.lexeme_fields)),
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
