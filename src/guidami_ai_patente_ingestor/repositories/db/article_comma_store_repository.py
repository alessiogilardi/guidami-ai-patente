from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.knowledge import ArticleComma

from ._bulk_insert_store_repository import BulkInsertStoreRepository

_ARTICLE_COMMA_TABLE_COLUMNS = (
    "article_id",
    "comma_number",
    "position",
    "text",
    "is_repealed",
    "embedding",
)


class ArticleCommaStoreRepository(BulkInsertStoreRepository[ArticleComma]):
    """Writes to `article_commas`.

    Two reset modes:
    - `delete_source`: full reload of a single source (used by the per-source flow).
    - `truncate`: wipes the entire table (used by `reset-knowledge-db`).
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_ARTICLE_COMMA_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
            client=client,
        )

    def delete_source(self, source: str) -> None:
        """Deletes the commas of the given `source` only, ahead of a per-source full reload.

        `article_commas` has no `source` column of its own (only via its parent
        `articles.source`), so the deletion goes through a subquery on `articles`.
        """
        query = sql.SQL(
            "DELETE FROM {table} WHERE article_id IN (SELECT id FROM articles WHERE source = %s)"
        ).format(table=sql.Identifier(self._table_name))
        self._client.execute(query, [source])

    @staticmethod
    def _to_db_row(item: ArticleComma) -> tuple[object, ...]:
        return (
            item.article_id,
            item.comma_number,
            item.position,
            item.text,
            item.is_repealed,
            item.embedding,
        )
