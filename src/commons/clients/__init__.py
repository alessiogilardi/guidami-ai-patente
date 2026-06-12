"""Client per servizi esterni (embedding, vector store)."""

from .embedding_client import E5SmallEmbeddingClient, EmbeddingClient
from .vector_store_client import VectorStoreClient

__all__ = ["E5SmallEmbeddingClient", "EmbeddingClient", "VectorStoreClient"]
