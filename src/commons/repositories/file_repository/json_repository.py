import json
from pathlib import Path

from ._base_file_repository import BaseFileRepository


class JsonRepository[T](BaseFileRepository[T]):
    """Concrete repository implementation for JSON file persistence."""

    def _read_raw(self, file_name: str | Path) -> dict | list:
        """Read and parse a JSON file from disk."""
        return json.loads(self._file_system_client.read_text(file_name))

    def _write_raw(self, data: dict | list, file_name: str | Path) -> None:
        """Serialize data to JSON and write it to disk, creating parent directories."""
        self._file_system_client.write_text(
            file_name, json.dumps(data, ensure_ascii=False, indent=2)
        )
