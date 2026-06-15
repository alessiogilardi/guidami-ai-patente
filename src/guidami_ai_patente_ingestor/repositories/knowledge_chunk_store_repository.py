from psycopg import sql

from commons.clients import PostgresClient
from commons.entities.knowledge import KnowledgeChunk


class KnowledgeChunkStoreRepository:
    """Scrittura full-reload su `knowledge_chunks` (truncate + bulk insert)."""

    def __init__(self, client: PostgresClient, table_name: str) -> None:
        """Inietta il `PostgresClient` e il nome della tabella."""
        self._client = client
        self._table_name = table_name

    def truncate(self) -> None:
        """Svuota la tabella in vista di un full reload."""
        self._client.truncate(self._table_name)

    def bulk_insert(self, chunks: list[KnowledgeChunk]) -> None:
        """Inserisce in batch i chunk del corpus, embedding incluso."""
        if not chunks:
            return

        query = sql.SQL(
            "INSERT INTO {table} "
            "(source, article_number, article_title, comma_index, chunk_text, "
            "is_repealed, source_url, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
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
                    chunk.is_repealed,
                    chunk.source_url,
                    chunk.embedding,
                )
                for chunk in chunks
            ],
        )
