"""Client per servizi esterni (embedding, Postgres)."""

from .embeddings import E5SmallEmbeddingClient, EmbeddingClient, LiteLLMEmbeddingClient
from .postgres_client import PostgresClient

__all__ = ["E5SmallEmbeddingClient", "EmbeddingClient", "LiteLLMEmbeddingClient", "PostgresClient"]
