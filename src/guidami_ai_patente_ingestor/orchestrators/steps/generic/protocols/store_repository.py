from typing import Any, Protocol


class StoreRepository(Protocol):
    """Minimal contract for a full-reload store (truncate + bulk insert).

    Structurally satisfied by KnowledgeChunkStoreRepository and
    QuizQuestionStoreRepository (no explicit inheritance).
    """

    def truncate(self) -> None:
        """Empties the table ahead of a full reload."""
        ...

    def bulk_insert(self, items: list[Any], /) -> None:
        """Bulk-inserts the items (positional-only: decouples from the concrete param name)."""
        ...
