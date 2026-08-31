"""Lazy DI builders for the `ingest` CLI.

Providers/clients are built per command (not eagerly in `main()`), so `reset` and
`status` run without `OPENROUTER_API_KEY`, and a Postgres connection failure only
affects the command that actually needs it.
"""

from typing import NamedTuple

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.clients import PostgresClient
from commons.repositories.db import CorpusReadRepository, QuizReadRepository
from guidami_ai_patente_ingestor.configs import IngestorConfig
from guidami_ai_patente_ingestor.providers import LayerResolverProvider
from guidami_ai_patente_ingestor.repositories import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
    QuizImageStoreRepository,
    QuizQuestionStoreRepository,
)


class EvaluationRepositories(NamedTuple):
    """The two read repositories `ingest evaluate retrieval` needs (AD-7)."""

    corpus: CorpusReadRepository
    quiz: QuizReadRepository


def build_layer_resolver(config: IngestorConfig) -> LayerResolverProvider:
    """Builds the `LayerResolverProvider` from the configured layers and source catalog."""
    return LayerResolverProvider(layers=config.layers, sources=config.sources)


def build_open_router_provider(config: IngestorConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.open_router_config.api_key.get_secret_value())


def build_postgres_client(config: IngestorConfig) -> PostgresClient:
    """Opens a Postgres connection. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config.postgres)


def build_health_repositories(
    config: IngestorConfig, postgres_client: PostgresClient
) -> dict[
    str,
    ArticleStoreRepository
    | ArticleCommaStoreRepository
    | QuizQuestionStoreRepository
    | QuizImageStoreRepository,
]:
    """Builds the table-name -> repository map consumed by `TableHealthChecker`."""
    return {
        config.articles_table: ArticleStoreRepository(config.articles_table, postgres_client),
        config.article_commas_table: ArticleCommaStoreRepository(
            config.article_commas_table, postgres_client
        ),
        config.quiz_questions_table: QuizQuestionStoreRepository(
            config.quiz_questions_table, postgres_client
        ),
        config.quiz_images_table: QuizImageStoreRepository(
            config.quiz_images_table, postgres_client
        ),
    }


def build_evaluation_repositories(
    config: IngestorConfig, postgres_client: PostgresClient
) -> EvaluationRepositories:
    """Builds the corpus and quiz read repositories the evaluation harness needs (AD-7)."""
    return EvaluationRepositories(
        corpus=CorpusReadRepository(
            config.articles_table, config.article_commas_table, postgres_client
        ),
        quiz=QuizReadRepository(
            config.quiz_questions_table,
            config.quiz_question_embeddings_table,
            config.quiz_images_table,
            postgres_client,
        ),
    )
