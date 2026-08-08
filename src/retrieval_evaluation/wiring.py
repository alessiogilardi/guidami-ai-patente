"""Lazy DI builders for the `evaluate-retrieval-judge` script."""

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.ai.observability import LlmCallLogRepository, QueuedLlmCallTracker
from commons.clients import PostgresClient
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from guidami_ai_patente_ingestor.configs import IngestorConfig

from .agents import RetrievalJudgeAgent


def build_open_router_provider(config: IngestorConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.open_router_config.api_key.get_secret_value())


def build_postgres_client(config: IngestorConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config.postgres)


def build_tracker(postgres_client: PostgresClient) -> QueuedLlmCallTracker:
    """Builds the queued LLM call tracker, persisted through the given client."""
    return QueuedLlmCallTracker(LlmCallLogRepository(postgres_client))


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
