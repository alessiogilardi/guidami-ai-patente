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
        """Read the entire content of a text file.

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
            content = safe_path.read_text(encoding=encoding)
        except (PermissionError, FileNotFoundError):
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error reading '{path}': {exc}")
            raise
        logger.debug(f"Finished reading text from '{path}'")
        return content

    def read_bytes(self, path: str | Path) -> bytes:
        """Read the entire content of a binary file.

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
            data = safe_path.read_bytes()
        except (PermissionError, FileNotFoundError):
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error reading '{path}': {exc}")
            raise
        logger.debug(f"Finished reading bytes from '{path}'")
        return data

    def read_stream(self, path: str | Path, chunk_size: int = 8192) -> Iterator[bytes]:
        """Stream a binary file in fixed-size chunks.

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
        logger.debug(f"Opening stream for reading '{path}'")
        safe_path = self._get_safe_read_path(path)
        with safe_path.open(mode="rb") as f:
            logger.debug(f"Stream opened for '{path}'")
            while chunk := f.read(chunk_size):
                yield chunk
        logger.debug(f"Stream closed for '{path}'")

    def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None:
        """Write a string to a text file, overwriting any existing content.

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
            safe_path.write_text(content, encoding=encoding)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing '{path}': {exc}")
            raise
        logger.debug(f"Finished writing text to '{path}'")

    def write_bytes(self, path: str | Path, data: bytes) -> None:
        """Write raw bytes to a binary file, overwriting any existing content.

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
            safe_path.write_bytes(data)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing '{path}': {exc}")
            raise
        logger.debug(f"Finished writing bytes to '{path}'")

    def write_stream(self, path: str | Path, data: Iterable[bytes]) -> None:
        """Write a stream of byte chunks to a file, overwriting any existing content.

        Parent directories are created automatically if absent.

        Args:
            path: Path relative to the base directory.
            data: Iterable of byte chunks to write sequentially.

        Raises:
            PermissionError: If path traversal is detected.
            OSError: If an unexpected I/O error occurs.
        """
        logger.debug(f"Opening stream for writing '{path}'")
        safe_path = self._get_safe_write_path(path)
        try:
            with safe_path.open(mode="wb") as f:
                logger.debug(f"Stream opened for writing '{path}'")
                for chunk in data:
                    f.write(chunk)
        except PermissionError:
            raise
        except OSError as exc:
            logger.error(f"Unexpected I/O error writing stream to '{path}': {exc}")
            raise
        logger.debug(f"Stream closed for '{path}'")

    def exists(self, path: str | Path) -> None:
        """Validate that a file is accessible under the base directory.

        Args:
            path: Path relative to the base directory.

        Returns:
            ``None`` if the file exists and is safely accessible.

        Raises:
            PermissionError: If path traversal is detected (checked first).
            FileNotFoundError: If the file does not exist.
        """
        self._get_safe_read_path(path)
