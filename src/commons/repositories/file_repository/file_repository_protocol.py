from collections.abc import Sequence
from pathlib import Path
from typing import Protocol


class FileRepository[T](Protocol):
    """Abstract repository interface following the Dependency Inversion Principle.

    The domain depends on this protocol, not on a concrete format implementation.
    """

    def load_one(self, file_name: str | Path) -> T:
        """Load and deserialize a single object from a file."""
        ...

    def load_list(self, file_name: str | Path) -> list[T]:
        """Load and deserialize a list of objects from a file."""
        ...

    def load_dir(self, dir_path: str | Path) -> list[T]:
        """Load every file of a directory as one object each, ordered by filename."""
        ...

    def write_one(self, item: T, file_name: str | Path) -> None:
        """Serialize and write a single object to a file."""
        ...

    def write_list(self, items: Sequence[T], file_name: str | Path) -> None:
        """Serialize and write a sequence of objects to a file."""
        ...
