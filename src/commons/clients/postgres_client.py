from collections.abc import Sequence
from types import TracebackType

from pgvector.psycopg import register_vector
from psycopg import Connection, sql
from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from commons.configs import PostgresConnectionConfig


def _configure(connection: Connection) -> None:
    """Registers the pgvector adapter on a freshly opened pooled connection.

    The adapter is per-connection state, so it must be re-registered every time the
    pool opens one; AD-13 depends on a VECTOR column deserialising without bespoke
    parsing.
    """
    register_vector(connection)


def _reset(connection: Connection) -> None:
    """Asserts the borrow left no session state behind (D4).

    With a single connection, a `SET`, a temp table or a prepared statement was private
    to the process by construction. Pooled, whatever one borrower leaves behind is
    inherited by the next. No `PostgresClient` caller may rely on session state — this
    hook exists to state that invariant where the next reader will find it, and is the
    place to add a real `ROLLBACK`/`DISCARD` if one ever does.
    """


class PostgresClient:
    """Generic, table-agnostic psycopg wrapper over a pooled connection (AD-26).

    Holds a `psycopg_pool.ConnectionPool` rather than a single connection: psycopg3
    guards a connection with an internal lock, so one connection would serialise every
    threaded SQL stage behind every other one. Connections are opened with
    `autocommit=True` and `register_vector` applied through `configure=`, preserving
    the single-connection behaviour every existing caller was written against.
    """

    def __init__(self, config: PostgresConnectionConfig) -> None:
        """Opens the pool and registers the pgvector adapter per connection."""
        conninfo = make_conninfo(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            dbname=config.dbname,
            sslmode=config.sslmode,
            connect_timeout=config.connect_timeout,
        )
        self._pool = ConnectionPool(
            conninfo,
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
            kwargs={"autocommit": True},
            configure=_configure,
            reset=_reset,
            timeout=config.connect_timeout,
            open=False,
        )
        # D3: `open=True` would open connections in a background worker and return
        # without raising, turning an unreachable database from an immediate
        # OperationalError into a PoolTimeout ~30s later, at the first query. Opening
        # eagerly with wait=True preserves the single-connection failure mode every
        # caller — `ingest status --online` above all — was written against.
        self._pool.open(wait=True, timeout=config.connect_timeout)

    def __enter__(self) -> "PostgresClient":
        """Allows use as a context manager (closes the pool on exit)."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Closes the pool when exiting the `with` block."""
        self.close()

    def close(self) -> None:
        """Closes every pooled connection."""
        self._pool.close()

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
        with self._pool.connection() as connection:
            connection.execute(query)

    def execute(
        self, query: sql.SQL | sql.Composed, params: Sequence[object] | None = None
    ) -> None:
        """Executes `query` once (statement with no result, e.g. parameterized DELETE)."""
        with self._pool.connection() as connection:
            connection.execute(query, params)

    def execute_many(
        self, query: sql.SQL | sql.Composed, params_seq: Sequence[Sequence[object]]
    ) -> None:
        """Executes `query` once for each row of `params_seq`."""
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.executemany(query, params_seq)

    def execute_many_returning(
        self, query: sql.SQL | sql.Composed, params_seq: Sequence[Sequence[object]]
    ) -> list[tuple]:
        """Executes `query` once per row of `params_seq`.

        Collects each statement's RETURNING rows, in the same order as `params_seq`.
        """
        with self._pool.connection() as connection, connection.cursor() as cursor:
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
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
