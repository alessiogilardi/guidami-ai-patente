from abc import ABC, abstractmethod


class EmbeddingClient(ABC):
    """Interfaccia per il calcolo di embedding di query e passaggi testuali."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Calcola l'embedding di una query utente."""

    @abstractmethod
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Calcola gli embedding di un batch di passaggi (chunk del corpus)."""
