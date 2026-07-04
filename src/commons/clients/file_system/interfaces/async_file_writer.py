"""Asynchronous file writer interface (ABC)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable
from pathlib import Path


class AsyncFileWriterInterface(ABC):
    """Interface (port) for asynchronous file write operations.

    Consumers that only need to write files asynchronously depend on this
    interface alone, following the Interface Segregation Principle.
    """

    @abstractmethod
    async def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Write a string to a text file asynchronously, overwriting any existing content.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the client's base directory.
            content: Text content to write.
            encoding: Character encoding to use when encoding. Defaults to ``"utf-8"``.

        Raises:
            PermissionError: If path traversal is detected.
        """

    @abstractmethod
    async def write_bytes(self, path: str | Path, data: bytes) -> None:
        """Write raw bytes to a binary file asynchronously, overwriting any existing content.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the client's base directory.
            data: Binary content to write.

        Raises:
            PermissionError: If path traversal is detected.
        """

    @abstractmethod
    async def write_stream(self, path: str | Path, data: AsyncIterable[bytes]) -> None:
        """Write an async stream of byte chunks to a file asynchronously.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the client's base directory.
            data: Async iterable of byte chunks to write sequentially.

        Raises:
            PermissionError: If path traversal is detected.
        """
