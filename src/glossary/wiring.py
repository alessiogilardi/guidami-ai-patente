"""Builds the handful of commons primitives pywire has no constructor recipe for.

`main.py`/`translate_main.py` build these once and register the built instances
(`register_instance`); every glossary-owned agent/service/repository then autowires
them like any other dependency (AD-1a).
"""

from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.embedding import EmbeddingService
from commons.ai.embedding.clients import LiteLLMEmbeddingClient
from commons.ai.embedding.configs import EmbeddingClientConfig
from commons.clients import PostgresClient
from commons.configs import OpenRouterConfig, PostgresConnectionConfig
from glossary.configs import GlossaryEmbeddingConfig


def build_open_router_provider(config: OpenRouterConfig) -> OpenRouterProvider:
    """Builds the OpenRouter provider from the configured API key."""
    return OpenRouterProvider(api_key=config.api_key.get_secret_value())


def build_postgres_client(config: PostgresConnectionConfig) -> PostgresClient:
    """Opens a Postgres connection pool. Raises `psycopg.Error` if unreachable."""
    return PostgresClient(config)


def build_embedding_service(config: GlossaryEmbeddingConfig) -> EmbeddingService:
    r"""Builds the embedder used for `f'{term}\n{definition}'` (FR-6)."""
    return EmbeddingService(config.batch_size, LiteLLMEmbeddingClient(EmbeddingClientConfig()))
