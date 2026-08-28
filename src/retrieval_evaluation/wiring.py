"""Lazy DI builders for the `evaluate-retrieval-judge` and `label-golden-set` scripts."""

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import PostgresLlmCallLogRepository, QueuedLlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from guidami_ai_patente_ingestor.configs import IngestorConfig

from .agents import CommaLabelerAgent, RetrievalJudgeAgent
from .repositories import GoldenSetWriteRepository


def build_open_router_provider(config: IngestorConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.open_router_config.api_key.get_secret_value())


def build_postgres_client(config: IngestorConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config.postgres)


def build_tracker(postgres_client: PostgresClient) -> QueuedLlmCallTracker:
    """Builds the queued LLM call tracker, persisted through the given client."""
    repository = PostgresLlmCallLogRepository("llm_call_logs", postgres_client)
    return QueuedLlmCallTracker(10.0, repository)


def build_quiz_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> QuizReadRepository:
    """Builds the quiz read repository, reusing the ingestor's table names."""
    return QuizReadRepository(
        config.quiz_questions_table,
        config.quiz_question_embeddings_table,
        config.quiz_images_table,
        postgres_client,
    )


def build_corpus_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> CorpusReadRepository:
    """Builds the corpus read repository, reusing the ingestor's table names."""
    return CorpusReadRepository(
        config.articles_table, config.article_commas_table, postgres_client
    )


def build_agent(
    config: IngestorConfig, provider: OpenRouterProvider, tracker: QueuedLlmCallTracker
) -> RetrievalJudgeAgent:
    """Loads `retrieval_judge.yaml` from the ingestor's configured `agents_dir`."""
    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    return RetrievalJudgeAgent.from_yaml(
        "retrieval_judge", agents_repository, provider, tracker=tracker
    )


def build_comma_labeler_config(config: IngestorConfig) -> AgentConfig:
    """Loads `comma_labeler.yaml` from the ingestor's configured `agents_dir`."""
    agents_repository = YamlRepository(
        AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir)
    )
    return agents_repository.load_one("comma_labeler.yaml")


def build_comma_labeler_agent(
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


def build_golden_set_repository(
    config: IngestorConfig, postgres_client: PostgresClient
) -> GoldenSetWriteRepository:
    """Builds the golden-set write repository, reusing the ingestor's table names."""
    return GoldenSetWriteRepository(
        config.labeling_runs_table,
        config.quiz_labelings_table,
        config.quiz_comma_labels_table,
        postgres_client,
    )
