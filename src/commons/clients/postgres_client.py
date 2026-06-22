from collections.abc import Sequence
from types import TracebackType

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo

from commons.configs import PostgresConnectionConfig


class PostgresClient:
    """Wrapper psycopg generico e table-agnostic, con adapter pgvector registrato."""

    def __init__(self, config: PostgresConnectionConfig) -> None:
        """Apre la connessione e registra l'adapter pgvector."""
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

    def __enter__(self) -> "PostgresClient":
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

    def truncate(self, table_name: str) -> None:
        """Svuota la tabella `table_name` in vista di un full reload."""
        query = sql.SQL("TRUNCATE TABLE {table}").format(table=sql.Identifier(table_name))
        self._connection.execute(query)

    def execute(self, query: sql.Composed, params: Sequence[object] | None = None) -> None:
        """Esegue `query` una sola volta (statement senza risultato, es. DELETE parametrico)."""
        self._connection.execute(query, params)

    def execute_many(self, query: sql.Composed, params_seq: Sequence[Sequence[object]]) -> None:
        """Esegue `query` una volta per ciascuna riga di `params_seq`."""
        with self._connection.cursor() as cursor:
            cursor.executemany(query, params_seq)

    def fetch(self, query: sql.Composed, params: Sequence[object] | None = None) -> list[tuple]:
        """Esegue `query` e ritorna tutte le righe del risultato."""
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
