from abc import ABC, abstractmethod


class EmbeddingClient(ABC):
    """Interface for computing embeddings of queries and text passages."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Computes the embedding of a user query."""

    @abstractmethod
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Computes the embeddings of a batch of passages (corpus chunks)."""
