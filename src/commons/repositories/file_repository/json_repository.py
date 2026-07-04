import json
from pathlib import Path

from ._base_file_repository import BaseFileRepository


class JsonRepository[T](BaseFileRepository[T]):
    """Concrete repository implementation for JSON file persistence."""

    def _read_raw(self, path: Path) -> dict | list:
        """Read and parse a JSON file from disk."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_raw(self, data: dict | list, path: Path) -> None:
        """Serialize data to JSON and write it to disk, creating parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
