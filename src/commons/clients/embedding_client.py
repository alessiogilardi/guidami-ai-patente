from abc import ABC, abstractmethod

from sentence_transformers import SentenceTransformer

from commons.configs import EmbeddingConfig


class EmbeddingClient(ABC):
    """Interfaccia per il calcolo di embedding di query e passaggi testuali."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Calcola l'embedding di una query utente."""

    @abstractmethod
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Calcola gli embedding di un batch di passaggi (chunk del corpus)."""


class E5SmallEmbeddingClient(EmbeddingClient):
    """Implementazione locale basata su intfloat/multilingual-e5-small."""

    def __init__(self, config: EmbeddingConfig) -> None:
        """Carica il modello sentence-transformers indicato in config."""
        self._config = config
        self._model = SentenceTransformer(config.model_name)

    def embed_query(self, text: str) -> list[float]:
        """Calcola l'embedding di una query utente."""
        vector = self._model.encode(
            f"{self._config.query_prefix}{text}", normalize_embeddings=True
        )
        return vector.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Calcola gli embedding di un batch di passaggi (chunk del corpus)."""
        prefixed = [f"{self._config.passage_prefix}{text}" for text in texts]
        vectors = self._model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()
