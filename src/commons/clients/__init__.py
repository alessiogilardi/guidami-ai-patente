"""Client per servizi esterni (embedding, Postgres)."""

from .embeddings import EmbeddingClient, LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
from .postgres_client import PostgresClient

__all__ = [
    "EmbeddingClient",
    "LiteLLMEmbeddingClient",
    "PostgresClient",
    "SentenceTransformerEmbeddingClient",
]
