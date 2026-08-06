from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from psycopg import sql

from commons.clients import PostgresClient


class UpsertStoreRepository[T](ABC):
    """Generic DB repository for stores based on `INSERT ... ON CONFLICT` (upsert)."""

    def __init__(
        self,
        table_name: str,
        columns: Sequence[str],
        conflict_columns: Sequence[str],
        row_mapper: Callable[[T], Sequence[object]],
        client: PostgresClient,
    ) -> None:
        """Configures table, target/conflict columns, item -> DB row mapping, and client."""
        if not columns:
            raise ValueError("columns must contain at least one column")
        if not conflict_columns:
            raise ValueError("conflict_columns must contain at least one column")

        unknown_conflict_columns = [column for column in conflict_columns if column not in columns]
        if unknown_conflict_columns:
            raise ValueError(
                f"conflict_columns must be a subset of columns, "
                f"unknown: {unknown_conflict_columns}"
            )

        self._client = client
        self._table_name = table_name
        self._columns = tuple(columns)
        self._conflict_columns = tuple(conflict_columns)
        self._update_columns = tuple(
            column for column in self._columns if column not in self._conflict_columns
        )
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

    def upsert(self, items: list[T]) -> None:
        """Batch-upserts the items on the configured conflict target."""
        if not items:
            return

        self._client.execute_many(
            self._upsert_query(),
            [self._row_mapper(item) for item in items],
        )

    def upsert_returning_ids(self, items: list[T]) -> list[int]:
        """Batch-upserts the items and returns their `id`, in input order.

        Raises:
            ValueError: if the table has no non-key column to update on conflict.
                `DO NOTHING` would then emit no row for a conflicting item,
                silently misaligning the returned ids with `items`.
        """
        if not self._update_columns:
            raise ValueError(
                f"{self._table_name}: upsert_returning_ids requires at least one "
                "non-key column, so a conflicting item still returns a row"
            )
        if not items:
            return []

        rows = self._client.execute_many_returning(
            self._upsert_query(returning="id"),
            [self._row_mapper(item) for item in items],
        )
        return [row[0] for row in rows]

    def table_exists(self) -> bool:
        """Checks whether the table exists (relies on the default `public` search_path)."""
        query = sql.SQL("SELECT to_regclass(%s) IS NOT NULL").format()
        rows = self._client.fetch(query, [self._table_name])
        return bool(rows[0][0])

    def row_count(self) -> int:
        """Returns the current row count of the table."""
        query = sql.SQL("SELECT count(*) FROM {table}").format(
            table=sql.Identifier(self._table_name)
        )
        rows = self._client.fetch(query)
        return rows[0][0]

    def _upsert_query(self, returning: str | None = None) -> sql.Composed:
        """Builds `INSERT ... ON CONFLICT (...) DO UPDATE/NOTHING [RETURNING ...]`."""
        query = sql.SQL(
            "INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            "ON CONFLICT ({conflict_columns})"
        ).format(
            table=sql.Identifier(self._table_name),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in self._columns),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in self._columns),
            conflict_columns=sql.SQL(", ").join(
                sql.Identifier(column) for column in self._conflict_columns
            ),
        )

        if self._update_columns:
            query += sql.SQL(" DO UPDATE SET {updates}").format(
                updates=sql.SQL(", ").join(
                    sql.SQL("{column} = EXCLUDED.{column}").format(column=sql.Identifier(column))
                    for column in self._update_columns
                )
            )
        else:
            query += sql.SQL(" DO NOTHING")

        if returning is not None:
            query += sql.SQL(" RETURNING {identifier}").format(
                identifier=sql.Identifier(returning)
            )

        return query

    @staticmethod
    @abstractmethod
    def _to_db_row(item: T) -> tuple[object, ...]: ...
