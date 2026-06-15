"""Client per servizi esterni (embedding, Postgres)."""

from .embedding_client import E5SmallEmbeddingClient, EmbeddingClient
from .postgres_client import PostgresClient

__all__ = ["E5SmallEmbeddingClient", "EmbeddingClient", "PostgresClient"]
