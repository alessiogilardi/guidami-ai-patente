from psycopg import sql

from commons.clients import PostgresClient
from commons.entities.knowledge import KnowledgeChunk

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
    """Scrittura su `knowledge_chunks`.

    Due modalita di reset:
    - `delete_source`: full-reload della singola source (usato dal flow per-source).
    - `truncate`: wipe dell'intera tabella (usato da `reset-knowledge-db`).
    """

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        super().__init__(
            client=client,
            table_name=table_name,
            columns=_KNOWLEDGE_CHUNK_TABLE_COLUMNS,
            row_mapper=self._to_db_row,
        )

    def delete_source(self, source: str) -> None:
        """Cancella i chunk della sola `source` in vista di un full reload per-source.

        Le altre source nella tabella restano intatte: l'indexing e per-source
        (una run per source), quindi non si puo fare TRUNCATE dell'intera tabella.
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
