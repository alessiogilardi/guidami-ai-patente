"""Base class for file system clients — path security only, no I/O."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


class BaseFileSystemClient:
    """Provides safe path resolution anchored to a base directory.

    All path operations are validated against the base directory to prevent
    path traversal attacks. Subclasses add I/O behaviour on top of these helpers.

    Args:
        base_directory: Root directory all relative paths are resolved against.
    """

    def __init__(self, base_directory: str | Path) -> None:
        self._base_directory = Path(base_directory).resolve()

    def _resolve_path(self, relative_path: str | Path) -> Path:
        """Resolve and validate a path against the base directory.

        Path traversal is detected by comparing the resolved absolute path
        against the resolved base directory with ``Path.is_relative_to``.

        Args:
            relative_path: Path relative to the base directory.

        Returns:
            Absolute resolved path (file need not exist).

        Raises:
            PermissionError: If path traversal is detected.
        """
        full_path = (self._base_directory / relative_path).resolve()
        if not full_path.is_relative_to(self._base_directory):
            logger.warning(f"Path traversal attempt detected for path: {relative_path!r}")
            raise PermissionError("Path traversal attempt detected.")
        return full_path

    def _get_safe_path(self, relative_path: str | Path, mode: Literal["r", "w"] = "r") -> Path:
        if mode == "w":
            return self._get_safe_write_path(relative_path)
        if mode == "r":
            return self._get_safe_read_path(relative_path)

        raise ValueError(f"Invalid mode: {mode}. Use 'r' or 'w'.")

    def _get_safe_read_path(self, relative_path: str | Path) -> Path:
        """Resolve, validate, and assert the file exists.

        Args:
            relative_path: Path relative to the base directory.

        Returns:
            Absolute resolved path to an existing file.

        Raises:
            PermissionError: If path traversal is detected.
            FileNotFoundError: If the resolved file does not exist.
        """
        path = self._resolve_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: '{relative_path}'")
        return path

    def _get_safe_write_path(self, relative_path: str | Path) -> Path:
        """Resolve, validate, and auto-create parent directories.

        Args:
            relative_path: Path relative to the base directory.

        Returns:
            Absolute resolved path (parent dirs created if absent).

        Raises:
            PermissionError: If path traversal is detected.
        """
        path = self._resolve_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _get_safe_dir_path(self, relative_path: str | Path) -> Path | None:
        """Resolve and validate a directory path; ``None`` if it does not exist.

        Args:
            relative_path: Path relative to the base directory.

        Returns:
            Absolute resolved path if it exists and is a directory, else ``None``.

        Raises:
            PermissionError: If path traversal is detected.
        """
        path = self._resolve_path(relative_path)
        return path if path.is_dir() else None

    def _list_files(self, dir_path: str | Path, pattern: str) -> list[Path]:
        """Shared listing logic for the sync and async clients.

        Args:
            dir_path: Directory (relative to the base directory) to list.
            pattern: Glob pattern to match files against.

        Returns:
            Sorted list of matching paths; ``[]`` if the directory does not exist.

        Raises:
            PermissionError: If path traversal is detected.
        """
        safe_dir = self._get_safe_dir_path(dir_path)
        if safe_dir is None:
            logger.debug("Directory '%s' does not exist, returning no files", dir_path)
            return []
        return sorted(safe_dir.glob(pattern))

    @contextmanager
    def _io_operation(self, path: str | Path, mode: Literal["r", "w"] = "r") -> Iterator[Path]:
        logger.debug("Starting I/O operation on '%s'", path)
        try:
            yield self._get_safe_path(path, mode)
        except (FileNotFoundError, PermissionError):
            logger.error("I/O operation failed on '%s'", path)
            raise
        except OSError:
            logger.exception("Unexpected I/O error on '%s'", path)
            raise
        finally:
            logger.debug("Finished I/O operation on '%s'", path)
