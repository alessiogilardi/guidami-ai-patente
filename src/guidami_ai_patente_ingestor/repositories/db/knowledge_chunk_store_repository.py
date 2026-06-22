from psycopg import sql

from commons.clients import PostgresClient
from commons.entities.knowledge import KnowledgeChunk


class KnowledgeChunkStoreRepository:
    """Scrittura su `knowledge_chunks`.

    Due modalità di reset:
    - `delete_source`: full-reload della singola source (usato dal flow per-source).
    - `truncate`: wipe dell'intera tabella (usato da `reset-knowledge-db`).
    """

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        self._client = client
        self._table_name = table_name

    def truncate(self) -> None:
        """Svuota l'intera tabella (wipe totale, non per-source)."""
        self._client.truncate(self._table_name)

    def delete_source(self, source: str) -> None:
        """Cancella i chunk della sola `source` in vista di un full reload per-source.

        Le altre source nella tabella restano intatte: l'indexing è per-source
        (una run per source), quindi non si può fare TRUNCATE dell'intera tabella.
        """
        query = sql.SQL("DELETE FROM {table} WHERE source = %s").format(
            table=sql.Identifier(self._table_name)
        )
        self._client.execute(query, [source])

    def bulk_insert(self, chunks: list[KnowledgeChunk]) -> None:
        """Inserisce in batch i chunk del corpus, embedding incluso."""
        if not chunks:
            return

        query = sql.SQL(
            "INSERT INTO {table} "
            "(source, article_number, article_title, comma_index, chunk_text, "
            "context, is_repealed, source_url, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        ).format(table=sql.Identifier(self._table_name))

        self._client.execute_many(
            query,
            [
                (
                    chunk.source,
                    chunk.article_number,
                    chunk.article_title,
                    chunk.comma_index,
                    chunk.chunk_text,
                    chunk.context,
                    chunk.is_repealed,
                    chunk.source_url,
                    chunk.embedding,
                )
                for chunk in chunks
            ],
        )
