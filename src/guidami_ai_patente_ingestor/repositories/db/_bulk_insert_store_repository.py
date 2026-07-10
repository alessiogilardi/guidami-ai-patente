from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from psycopg import sql

from commons.clients import PostgresClient


class BulkInsertStoreRepository[T](ABC):
    """Generic DB repository for stores based on truncate + bulk insert."""

    def __init__(
        self,
        table_name: str,
        columns: Sequence[str],
        row_mapper: Callable[[T], Sequence[object]],
        client: PostgresClient,
    ) -> None:
        """Configures table, target columns, item -> DB row mapping, and client."""
        if not columns:
            raise ValueError("columns must contain at least one column")

        self._client = client
        self._table_name = table_name
        self._columns = tuple(columns)
        self._row_mapper = row_mapper

    def truncate(self) -> None:
        """Empties the table ahead of a full reload."""
        self._client.truncate(self._table_name)

    def bulk_insert(self, items: list[T]) -> None:
        """Batch-inserts the items using the concrete mapper."""
        if not items:
            return

        query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
            table=sql.Identifier(self._table_name),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in self._columns),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in self._columns),
        )

        self._client.execute_many(
            query,
            [self._row_mapper(item) for item in items],
        )

    @staticmethod
    @abstractmethod
    def _to_db_row(item: T) -> tuple[object, ...]: ...
