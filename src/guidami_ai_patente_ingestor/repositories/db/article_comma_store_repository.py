from collections.abc import Sequence

from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.knowledge import ArticleCommaEntity

from ._upsert_store_repository import UpsertStoreRepository

_ARTICLE_COMMA_TABLE_COLUMNS = (
    "article_id",
    "comma_number",
    "position",
    "text",
    "is_repealed",
    "embedding",
)
_ARTICLE_COMMA_CONFLICT_COLUMNS = ("article_id", "comma_number")


class ArticleCommaStoreRepository(UpsertStoreRepository[ArticleCommaEntity]):
    """Writes to `article_commas` via upsert on `(article_id, comma_number)`.

    Plus scoped reconciliation. `truncate` remains available for
    `reset-knowledge-db`'s full wipe.
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_ARTICLE_COMMA_TABLE_COLUMNS,
            conflict_columns=_ARTICLE_COMMA_CONFLICT_COLUMNS,
            client=client,
        )

    def delete_missing(
        self, article_ids: Sequence[int], present: Sequence[ArticleCommaEntity]
    ) -> None:
        """Deletes commas of `article_ids` whose `(article_id, comma_number)` is not in `present`.

        Returns immediately when `article_ids` is empty. Both `%s::bigint[]`/`%s::text[]`
        casts are passed even when `present` is empty, so `NOT EXISTS` correctly deletes
        every comma of those articles in that case.
        """
        if not article_ids:
            return

        query = sql.SQL(
            "DELETE FROM {table} c "
            "WHERE c.article_id = ANY(%s) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM unnest(%s::bigint[], %s::text[]) AS k(article_id, comma_number) "
            "WHERE k.article_id = c.article_id AND k.comma_number = c.comma_number"
            ")"
        ).format(table=sql.Identifier(self._table_name))
        self._client.execute(
            query,
            [
                list(article_ids),
                [comma.article_id for comma in present],
                [comma.comma_number for comma in present],
            ],
        )

    @staticmethod
    def _to_db_row(item: ArticleCommaEntity) -> tuple[object, ...]:
        return (
            item.article_id,
            item.comma_number,
            item.position,
            item.text,
            item.is_repealed,
            item.embedding,
        )
