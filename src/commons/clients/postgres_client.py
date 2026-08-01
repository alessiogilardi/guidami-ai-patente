from collections.abc import Sequence
from types import TracebackType

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.conninfo import make_conninfo

from commons.configs import PostgresConnectionConfig


class PostgresClient:
    """Generic, table-agnostic psycopg wrapper with the pgvector adapter registered."""

    def __init__(self, config: PostgresConnectionConfig) -> None:
        """Opens the connection and registers the pgvector adapter."""
        conninfo = make_conninfo(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            dbname=config.dbname,
            sslmode=config.sslmode,
            connect_timeout=config.connect_timeout,
        )
        self._connection = psycopg.connect(conninfo, autocommit=True)
        register_vector(self._connection)

    def __enter__(self) -> "PostgresClient":
        """Allows use as a context manager (closes the connection on exit)."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Closes the connection when exiting the `with` block."""
        self.close()

    def close(self) -> None:
        """Closes the database connection."""
        self._connection.close()

    def truncate(self, *table_names: str) -> None:
        """Empties the given tables in preparation for a full reload.

        Emits a single combined `TRUNCATE TABLE t1, t2, ...` statement when multiple
        names are given, so tables linked by a foreign key are truncated atomically in
        one statement (Postgres refuses to truncate a table referenced by a live FK
        constraint via a separate `TRUNCATE` statement, regardless of ordering).
        """
        query = sql.SQL("TRUNCATE TABLE {tables}").format(
            tables=sql.SQL(", ").join(sql.Identifier(name) for name in table_names)
        )
        self._connection.execute(query)

    def execute(
        self, query: sql.SQL | sql.Composed, params: Sequence[object] | None = None
    ) -> None:
        """Executes `query` once (statement with no result, e.g. parameterized DELETE)."""
        self._connection.execute(query, params)

    def execute_many(
        self, query: sql.SQL | sql.Composed, params_seq: Sequence[Sequence[object]]
    ) -> None:
        """Executes `query` once for each row of `params_seq`."""
        with self._connection.cursor() as cursor:
            cursor.executemany(query, params_seq)

    def execute_many_returning(
        self, query: sql.SQL | sql.Composed, params_seq: Sequence[Sequence[object]]
    ) -> list[tuple]:
        """Executes `query` once per row of `params_seq`.

        Collects each statement's RETURNING rows, in the same order as `params_seq`.
        """
        with self._connection.cursor() as cursor:
            cursor.executemany(query, params_seq, returning=True)
            rows: list[tuple] = []
            while True:
                rows.extend(cursor.fetchall())
                if not cursor.nextset():
                    break
            return rows

    def fetch(
        self, query: sql.SQL | sql.Composed, params: Sequence[object] | None = None
    ) -> list[tuple]:
        """Executes `query` and returns all result rows."""
        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
