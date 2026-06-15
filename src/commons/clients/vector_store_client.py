from types import TracebackType

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo

from commons.configs import VectorStoreConfig
from commons.models.knowledge import KnowledgeChunk, RetrievalResult


class VectorStoreClient:
    """Wrapper psycopg + pgvector sulla tabella `knowledge_chunks`."""

    def __init__(self, config: VectorStoreConfig) -> None:
        """Apre la connessione e registra l'adapter pgvector."""
        self._config = config

        conninfo = make_conninfo(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            dbname=config.dbname,
            sslmode=config.sslmode,
        )
        self._connection = psycopg.connect(conninfo, autocommit=True)
        register_vector(self._connection)

    def __enter__(self) -> "VectorStoreClient":
        """Permette l'uso come context manager (chiude la connessione in uscita)."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Chiude la connessione all'uscita dal blocco `with`."""
        self.close()

    def close(self) -> None:
        """Chiude la connessione al database."""
        self._connection.close()

    def truncate(self) -> None:
        """Svuota la tabella in vista di un full reload."""
        query = sql.SQL("TRUNCATE TABLE {table}").format(
            table=sql.Identifier(self._config.table_name)
        )
        self._connection.execute(query)

    def bulk_insert(self, chunks: list[KnowledgeChunk]) -> None:
        """Inserisce in batch i chunk del corpus, embedding incluso."""
        if not chunks:
            return

        query = sql.SQL(
            "INSERT INTO {table} "
            "(source, article_number, article_title, comma_index, chunk_text, "
            "is_repealed, source_url, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        ).format(table=sql.Identifier(self._config.table_name))

        with self._connection.cursor() as cursor:
            cursor.executemany(
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

    def similarity_search(
        self, embedding: list[float], top_k: int, source: str | None = None
    ) -> list[RetrievalResult]:
        """Ricerca per similarità coseno, opzionalmente filtrata per `source`."""
        table = sql.Identifier(self._config.table_name)
        where = sql.SQL("WHERE source = %s") if source is not None else sql.SQL("")
        query = sql.SQL(
            "SELECT source, article_number, article_title, comma_index, chunk_text, "
            "is_repealed, source_url, embedding, 1 - (embedding <=> %s::vector) AS score "
            "FROM {table} {where} ORDER BY embedding <=> %s::vector LIMIT %s"
        ).format(table=table, where=where)

        params: list[object] = [embedding]
        if source is not None:
            params.append(source)
        params.extend([embedding, top_k])

        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            RetrievalResult(
                chunk=KnowledgeChunk(
                    source=row[0],
                    article_number=row[1],
                    article_title=row[2],
                    comma_index=row[3],
                    chunk_text=row[4],
                    is_repealed=row[5],
                    source_url=row[6],
                    embedding=list(row[7]) if row[7] is not None else None,
                ),
                score=row[8],
            )
            for row in rows
        ]
