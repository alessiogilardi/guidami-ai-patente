"""Base class for file system clients — path security only, no I/O."""

import logging
from pathlib import Path

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
