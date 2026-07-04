from pathlib import Path

import yaml

from ._base_file_repository import BaseFileRepository


class YamlRepository[T](BaseFileRepository[T]):
    """Concrete repository implementation for YAML file persistence."""

    def _read_raw(self, path: Path) -> dict | list:
        """Read and parse a YAML file from disk."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _write_raw(self, data: dict | list, path: Path) -> None:
        """Serialize data to YAML and write it to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
