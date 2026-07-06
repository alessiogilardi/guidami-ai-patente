from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from psycopg import sql

from commons.clients import PostgresClient


class BulkInsertStoreRepository[T](ABC):
    """Repository DB generico per store basati su truncate + bulk insert."""

    def __init__(
        self,
        table_name: str,
        columns: Sequence[str],
        row_mapper: Callable[[T], Sequence[object]],
        client: PostgresClient,
    ) -> None:
        """Configura tabella, colonne target, mapping item -> riga DB e client."""
        if not columns:
            raise ValueError("columns must contain at least one column")

        self._client = client
        self._table_name = table_name
        self._columns = tuple(columns)
        self._row_mapper = row_mapper

    def truncate(self) -> None:
        """Svuota la tabella in vista di un full reload."""
        self._client.truncate(self._table_name)

    def bulk_insert(self, items: list[T]) -> None:
        """Inserisce in batch gli item configurati dal mapper concreto."""
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
