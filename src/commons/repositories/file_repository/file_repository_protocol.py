from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class FileRepository[T](Protocol):
    """Abstract repository interface following the Dependency Inversion Principle.

    The domain depends on this protocol, not on a concrete format implementation.
    """

    def load(self, file_name: str | Path) -> T | Sequence[T]:
        """Load and deserialize one or more objects from a file."""
        ...

    def write(self, data: T | Sequence[T], file_name: str | Path) -> None:
        """Serialize and write one object or a sequence to a file."""
        ...

    def load_all(self, dir_path: str | Path) -> list[T]:
        """Load every file of a directory as one object each, ordered by filename."""
        ...
