"""Asynchronous local file system client backed by aiofiles."""

import logging
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from ._base_file_system_client import BaseFileSystemClient
from .interfaces import AsyncFileReaderInterface, AsyncFileWriterInterface

logger = logging.getLogger(__name__)


class AsyncLocalFileSystemClient(
    BaseFileSystemClient, AsyncFileReaderInterface, AsyncFileWriterInterface
):
    """Concrete asynchronous adapter for local disk I/O using aiofiles.

    Implements both :class:`AsyncFileReaderInterface` and :class:`AsyncFileWriterInterface`.
    All paths are validated against the base directory to prevent path traversal.
    Path resolution is always synchronous; only the actual file I/O is awaited.

    Args:
        base_directory: Root directory all relative paths are resolved against.
    """

    async def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        """Read the entire content of a text file asynchronously."""
        with self._io_operation(path) as safe_path:
            async with aiofiles.open(safe_path, encoding=encoding) as f:
                content = await f.read()

        logger.debug(f"Finished reading text from '{path}'")
        return content

    async def read_bytes(self, path: str | Path) -> bytes:
        """Read the entire content of a binary file asynchronously."""
        with self._io_operation(path) as safe_path:
            async with aiofiles.open(safe_path, mode="rb") as f:
                data = await f.read()

        logger.debug(f"Finished reading bytes from '{path}'")
        return data

    async def read_stream(  # type: ignore[override]
        self, path: str | Path, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream a binary file in fixed-size chunks asynchronously."""
        with self._io_operation(path) as safe_path:
            async with aiofiles.open(safe_path, mode="rb") as f:
                logger.debug(f"Async stream opened for '{path}'")
                while chunk := await f.read(chunk_size):
                    yield chunk

        logger.debug(f"Async stream closed for '{path}'")

    async def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Write a string to a text file asynchronously, overwriting any existing content."""
        with self._io_operation(path, mode="w") as safe_path:
            async with aiofiles.open(safe_path, mode="w", encoding=encoding) as f:
                await f.write(content)

        logger.debug(f"Finished writing text to '{path}'")

    async def write_bytes(self, path: str | Path, data: bytes) -> None:
        """Write raw bytes to a binary file asynchronously, overwriting any existing content."""
        with self._io_operation(path, mode="w") as safe_path:
            async with aiofiles.open(safe_path, mode="wb") as f:
                await f.write(data)

        logger.debug(f"Finished writing bytes to '{path}'")

    async def write_stream(self, path: str | Path, data: AsyncIterable[bytes]) -> None:
        """Write an async stream of byte chunks to a file asynchronously."""
        with self._io_operation(path, mode="w") as safe_path:
            async with aiofiles.open(safe_path, mode="wb") as f:
                logger.debug(f"Async stream opened for writing '{path}'")
                async for chunk in data:
                    await f.write(chunk)

        logger.debug(f"Async stream closed for '{path}'")

    async def exists_or_raise(self, path: str | Path) -> None:
        """Validate that a file is accessible under the base directory asynchronously."""
        self._get_safe_read_path(path)
