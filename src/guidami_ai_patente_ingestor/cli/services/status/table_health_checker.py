from collections.abc import Mapping
from typing import Protocol

from ...models.status import TableHealth


class _HealthCapableRepository(Protocol):
    """Structural type for store repositories exposing the health read primitives."""

    def table_exists(self) -> bool: ...

    def row_count(self) -> int: ...


class TableHealthChecker:
    """Assembles `TableHealth` DTOs from health-capable store repositories (online only)."""

    def __init__(self, repositories: Mapping[str, _HealthCapableRepository]) -> None:
        """Injects a table-name -> health-capable-repository map."""
        self._repositories = repositories

    def check(self) -> list[TableHealth]:
        """Returns one `TableHealth` per repository; skips the row count when absent."""
        tables: list[TableHealth] = []
        for table, repository in self._repositories.items():
            exists = repository.table_exists()
            row_count = repository.row_count() if exists else None
            tables.append(TableHealth(table=table, exists=exists, row_count=row_count))
        return tables
