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
        """Read the entire content of a text file asynchronously.

        Args:
            path: Path relative to the base directory.
            encoding: Character encoding to use when decoding. Defaults to ``"utf-8"``.

        Returns:
            File content as a string.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Reading text from '{path}'")
        safe_path = self._get_safe_read_path(path)
        try:
            async with aiofiles.open(safe_path, encoding=encoding) as f:
                content = await f.read()
        except (PermissionError, FileNotFoundError):
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error reading '{path}': {exc}")
            raise
        logger.debug(f"Finished reading text from '{path}'")
        return content

    async def read_bytes(self, path: str | Path) -> bytes:
        """Read the entire content of a binary file asynchronously.

        Args:
            path: Path relative to the base directory.

        Returns:
            File content as raw bytes.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Reading bytes from '{path}'")
        safe_path = self._get_safe_read_path(path)
        try:
            async with aiofiles.open(safe_path, mode="rb") as f:
                data = await f.read()
        except (PermissionError, FileNotFoundError):
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error reading '{path}': {exc}")
            raise
        logger.debug(f"Finished reading bytes from '{path}'")
        return data

    async def read_stream(  # type: ignore[override]
        self, path: str | Path, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream a binary file in fixed-size chunks asynchronously.

        Args:
            path: Path relative to the base directory.
            chunk_size: Number of bytes per chunk. Defaults to 8192.

        Yields:
            Successive byte chunks until EOF.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the file does not exist.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Opening async stream for reading '{path}'")
        safe_path = self._get_safe_read_path(path)
        async with aiofiles.open(safe_path, mode="rb") as f:
            logger.debug(f"Async stream opened for '{path}'")
            while chunk := await f.read(chunk_size):
                yield chunk
        logger.debug(f"Async stream closed for '{path}'")

    async def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Write a string to a text file asynchronously, overwriting any existing content.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the base directory.
            content: Text content to write.
            encoding: Character encoding to use when encoding. Defaults to ``"utf-8"``.

        Raises:
            PermissionError: If path traversal is detected.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Writing text to '{path}'")
        safe_path = self._get_safe_write_path(path)
        try:
            async with aiofiles.open(safe_path, mode="w", encoding=encoding) as f:
                await f.write(content)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing '{path}': {exc}")
            raise
        logger.debug(f"Finished writing text to '{path}'")

    async def write_bytes(self, path: str | Path, data: bytes) -> None:
        """Write raw bytes to a binary file asynchronously, overwriting any existing content.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the base directory.
            data: Binary content to write.

        Raises:
            PermissionError: If path traversal is detected.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Writing bytes to '{path}'")
        safe_path = self._get_safe_write_path(path)
        try:
            async with aiofiles.open(safe_path, mode="wb") as f:
                await f.write(data)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing '{path}': {exc}")
            raise
        logger.debug(f"Finished writing bytes to '{path}'")

    async def write_stream(self, path: str | Path, data: AsyncIterable[bytes]) -> None:
        """Write an async stream of byte chunks to a file asynchronously.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the base directory.
            data: Async iterable of byte chunks to write sequentially.

        Raises:
            PermissionError: If path traversal is detected.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Opening async stream for writing '{path}'")
        safe_path = self._get_safe_write_path(path)
        try:
            async with aiofiles.open(safe_path, mode="wb") as f:
                logger.debug(f"Async stream opened for writing '{path}'")
                async for chunk in data:
                    await f.write(chunk)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing stream to '{path}': {exc}")
            raise
        logger.debug(f"Async stream closed for '{path}'")

    async def exists(self, path: str | Path) -> None:
        """Validate that a file is accessible under the base directory asynchronously.

        Path resolution is synchronous; this method is declared ``async`` for
        interface consistency.

        Args:
            path: Path relative to the base directory.

        Returns:
            ``None`` if the file exists and is safely accessible.

        Raises:
            PermissionError: If path traversal is detected (checked first).
            FileNotFoundError: If the file does not exist.
        """
        self._get_safe_read_path(path)
