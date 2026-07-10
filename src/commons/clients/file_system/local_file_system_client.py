"""Synchronous local file system client."""

import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

from ._base_file_system_client import BaseFileSystemClient
from .interfaces import FileReaderInterface, FileWriterInterface

logger = logging.getLogger(__name__)


class LocalFileSystemClient(BaseFileSystemClient, FileReaderInterface, FileWriterInterface):
    """Concrete synchronous adapter for local disk I/O.

    Implements both :class:`FileReaderInterface` and :class:`FileWriterInterface`.
    All paths are validated against the base directory to prevent path traversal.

    Args:
        base_directory: Root directory all relative paths are resolved against.
    """

    def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        """Read the entire content of a text file."""
        with self._io_operation(path) as safe_path:
            return safe_path.read_text(encoding=encoding)

    def read_bytes(self, path: str | Path) -> bytes:
        """Read the entire content of a binary file."""
        with self._io_operation(path) as safe_path:
            return safe_path.read_bytes()

    def read_stream(self, path: str | Path, chunk_size: int = 8192) -> Iterator[bytes]:
        """Stream a binary file in fixed-size chunks."""
        with self._io_operation(path) as safe_path, safe_path.open(mode="rb") as f:
            while chunk := f.read(chunk_size):
                yield chunk

    def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Write a string to a text file, overwriting any existing content."""
        with self._io_operation(path, mode="w") as safe_path:
            safe_path.write_text(content, encoding=encoding)

    def write_bytes(self, path: str | Path, data: bytes) -> None:
        """Write raw bytes to a binary file, overwriting any existing content."""
        with self._io_operation(path, mode="w") as safe_path:
            safe_path.write_bytes(data)

    def write_stream(self, path: str | Path, data: Iterable[bytes]) -> None:
        """Write a stream of byte chunks to a file, overwriting any existing content."""
        with self._io_operation(path, mode="w") as safe_path, safe_path.open(mode="wb") as f:
            for chunk in data:
                f.write(chunk)

    def exists_or_raise(self, path: str | Path) -> None:
        """Validate that a file is accessible under the base directory."""
        self._get_safe_read_path(path)
