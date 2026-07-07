from pathlib import Path

import yaml

from ._base_file_repository import BaseFileRepository


class YamlRepository[T](BaseFileRepository[T]):
    """Concrete repository implementation for YAML file persistence."""

    def _read_raw(self, file_name: str | Path) -> dict | list:
        """Read and parse a YAML file from disk."""
        return yaml.safe_load(self._file_system_client.read_text(file_name))

    def _write_raw(self, data: dict | list, file_name: str | Path) -> None:
        """Serialize data to YAML and write it to disk."""
        self._file_system_client.write_text(
            file_name, yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        )
