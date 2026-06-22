from typing import Any, Protocol


class StoreRepository(Protocol):
    """Contratto minimale di uno store full-reload (truncate + bulk insert).

    Soddisfatto strutturalmente da KnowledgeChunkStoreRepository e
    QuizQuestionStoreRepository (nessuna ereditarietà esplicita).
    """

    def truncate(self) -> None:
        """Svuota la tabella in vista di un full reload."""
        ...

    def bulk_insert(self, items: list[Any], /) -> None:
        """Inserisce in bulk gli item (positional-only: disaccoppia dal nome param concreto)."""
        ...
