from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.knowledge import ArticleEntity

from ._upsert_store_repository import UpsertStoreRepository

_ARTICLE_TABLE_COLUMNS = (
    "source",
    "number",
    "title",
    "url",
    "scraped_at",
    "is_repealed",
)
_ARTICLE_CONFLICT_COLUMNS = ("source", "number")


class ArticleStoreRepository(UpsertStoreRepository[ArticleEntity]):
    """Writes to `articles` via upsert on `(source, number)`, plus scoped reconciliation.

    `truncate` remains available for `reset-knowledge-db`'s full wipe.
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_ARTICLE_TABLE_COLUMNS,
            conflict_columns=_ARTICLE_CONFLICT_COLUMNS,
            client=client,
        )

    def delete_missing(self, source: str, present: Sequence[ArticleEntity]) -> None:
        """Deletes rows of `source` whose `number` is not among `present`.

        An empty `present` deletes every row of that source — the run legitimately
        produced nothing, and the table must mirror that.
        """
        query = sql.SQL("DELETE FROM {table} WHERE source = %s AND NOT (number = ANY(%s))").format(
            table=sql.Identifier(self._table_name)
        )
        self._client.execute(query, [source, [article.number for article in present]])

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
            item.scraped_at,
            item.is_repealed,
        )
