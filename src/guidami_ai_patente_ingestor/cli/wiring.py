"""Lazy DI builders for the `ingest` CLI.

Providers/clients are built per command (not eagerly in `main()`), so `reset` and
`status` run without `OPENROUTER_API_KEY`, and a Postgres connection failure only
affects the command that actually needs it.
"""

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.observability import (
    LlmCallLogRepository,
    QueuedLlmCallTracker,
)
from commons.clients import PostgresClient
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
    QuizQuestionStoreRepository,
)
from guidami_ai_patente_ingestor.services import LayerResolver


def build_layer_resolver(config: IngestorConfig) -> LayerResolver:
    """Builds the `LayerResolver` from the configured layers and source catalog."""
    return LayerResolver(layers=config.layers, sources=config.sources)


def build_open_router_provider(config: IngestorConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.open_router_config.api_key.get_secret_value())


def build_postgres_client(config: IngestorConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config.postgres)


def build_tracker(postgres_client: PostgresClient) -> QueuedLlmCallTracker:
    """Builds the queued LLM call tracker, persisted through the given client."""
    return QueuedLlmCallTracker(LlmCallLogRepository(postgres_client))


def build_health_repositories(
    config: IngestorConfig, postgres_client: PostgresClient
) -> dict[str, ArticleStoreRepository | ArticleCommaStoreRepository | QuizQuestionStoreRepository]:
    """Builds the table-name -> repository map consumed by `TableHealthChecker`."""
    return {
        config.articles_table: ArticleStoreRepository(config.articles_table, postgres_client),
        config.article_commas_table: ArticleCommaStoreRepository(
            config.article_commas_table, postgres_client
        ),
        config.quiz_questions_table: QuizQuestionStoreRepository(
            config.quiz_questions_table, postgres_client
        ),
    }
