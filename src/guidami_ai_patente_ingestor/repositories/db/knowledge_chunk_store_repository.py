from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.knowledge import KnowledgeChunk

from ._bulk_insert_store_repository import BulkInsertStoreRepository

_KNOWLEDGE_CHUNK_TABLE_COLUMNS = (
    "source",
    "article_number",
    "article_title",
    "comma_index",
    "chunk_text",
    "context",
    "is_repealed",
    "source_url",
    "embedding",
)


class KnowledgeChunkStoreRepository(BulkInsertStoreRepository[KnowledgeChunk]):
    """Writes to `knowledge_chunks`.

    Two reset modes:
    - `delete_source`: full reload of a single source (used by the per-source flow).
    - `truncate`: wipes the entire table (used by `reset-knowledge-db`).
    """

    def __init__(self, table_name: str, client: PostgresClient) -> None:
        """Injects the table name and the `PostgresClient`."""
        super().__init__(
            table_name=table_name,
            columns=_KNOWLEDGE_CHUNK_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
            client=client,
        )

    def delete_source(self, source: str) -> None:
        """Deletes the chunks of the given `source` only, ahead of a per-source full reload.

        The other sources in the table remain intact: indexing is per-source
        (one run per source), so the entire table cannot be TRUNCATEd.
        """
        query = sql.SQL("DELETE FROM {table} WHERE source = %s").format(
            table=sql.Identifier(self._table_name)
        )
        self._client.execute(query, [source])

    @staticmethod
    def _to_db_row(item: KnowledgeChunk) -> tuple[object, ...]:
        return (
            item.source,
            item.article_number,
            item.article_title,
            item.comma_index,
            item.chunk_text,
            item.context,
            item.is_repealed,
            item.source_url,
            item.embedding,
        )
