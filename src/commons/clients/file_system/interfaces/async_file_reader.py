"""Asynchronous file reader interface (ABC)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path


class AsyncFileReaderInterface(ABC):
    """Interface (port) for asynchronous file read operations.

    Consumers that only need to read files asynchronously depend on this
    interface alone, following the Interface Segregation Principle.
    """

    @abstractmethod
    async def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        """Read the entire content of a text file asynchronously.

        Args:
            path: Path relative to the client's base directory.
            encoding: Character encoding to use when decoding. Defaults to ``"utf-8"``.

        Returns:
            File content as a string.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
        """

    @abstractmethod
    async def read_bytes(self, path: str | Path) -> bytes:
        """Read the entire content of a binary file asynchronously.

        Args:
            path: Path relative to the client's base directory.

        Returns:
            File content as raw bytes.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
        """

    @abstractmethod
    def read_stream(self, path: str | Path, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """Stream a binary file in fixed-size chunks asynchronously.

        Args:
            path: Path relative to the client's base directory.
            chunk_size: Number of bytes per chunk. Defaults to 8192.

        Returns:
            Async iterator yielding successive byte chunks until EOF.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
        """

    @abstractmethod
    async def exists_or_raise(self, path: str | Path) -> None:
        """Validate that a file is accessible under the base directory asynchronously.

        Path resolution is synchronous internally; the method is declared ``async``
        for interface consistency with other async methods.

        Args:
            path: Path relative to the client's base directory.

        Returns:
            ``None`` if the file exists and is safely accessible.

        Raises:
            PermissionError: If path traversal is detected (checked first).
            FileNotFoundError: If the file does not exist.
        """
