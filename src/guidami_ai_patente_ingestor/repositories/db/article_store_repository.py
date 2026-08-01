from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.knowledge import ArticleEntity

from ._bulk_insert_store_repository import BulkInsertStoreRepository

_ARTICLE_TABLE_COLUMNS = (
    "source",
    "number",
    "title",
    "url",
    "is_repealed",
)


class ArticleStoreRepository(BulkInsertStoreRepository[ArticleEntity]):
    """Writes to `articles`.

    Two reset modes:
    - `delete_source`: full reload of a single source (used by the per-source flow).
    - `truncate`: wipes the entire table (used by `reset-knowledge-db`).
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_ARTICLE_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
            client=client,
        )

    def delete_source(self, source: str) -> None:
        """Deletes the articles of the given `source` only, ahead of a per-source full reload.

        The other sources in the table remain intact: indexing is per-source
        (one run per source), so the entire table cannot be TRUNCATEd.
        """
        query = sql.SQL("DELETE FROM {table} WHERE source = %s").format(
            table=sql.Identifier(self._table_name)
        )
        self._client.execute(query, [source])

    def bulk_insert_returning_ids(self, items: list[ArticleEntity]) -> list[int]:
        """Batch-inserts the items and returns their DB-generated ids.

        Ids are returned in the same order as `items`, one per input `ArticleEntity`.
        """
        query = sql.SQL(
            "INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
        ).format(
            table=sql.Identifier(self._table_name),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in self._columns),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in self._columns),
        )
        rows = self._client.execute_many_returning(
            query,
            [self._to_db_row(item) for item in items],
        )
        return [row[0] for row in rows]

    @staticmethod
    def _to_db_row(item: ArticleEntity) -> tuple[object, ...]:
        return (
            item.source,
            item.number,
            item.title,
            item.url,
            item.is_repealed,
        )
