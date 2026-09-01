from psycopg import sql

from commons.clients import PostgresClient

from ..entities import LlmCallLogEntity

# Insertable columns of the log table, in table order (see db/init.sql). `id` and
# `created_at` are DB-generated and excluded (entities-as-insertable-projection rule).
_COLUMNS = (
    "caller",
    "model",
    "system_prompt",
    "prompt",
    "response",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
    "status",
    "error_message",
    "latency_ms",
    "start_time",
    "end_time",
)


class PostgresLlmCallLogRepository:
    """Append-only `LlmCallLogRepository` writing to a Postgres table.

    Commons-level (unlike the ingestor's `*StoreRepository`s): the future FastAPI app
    will track calls too. Does not extend `UpsertStoreRepository` — its truncate/upsert/
    bulk-insert contract does not fit an append-only log.
    """

    def __init__(self, table: str, client: PostgresClient) -> None:
        """Stores the target table name and the DB client used to persist call logs."""
        self._client = client
        self._query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
            table=sql.Identifier(table),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in _COLUMNS),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in _COLUMNS),
        )

    def insert(self, log: LlmCallLogEntity) -> None:
        """Inserts one row. `Decimal` adapts to `NUMERIC` natively."""
        self._client.execute(self._query, self._to_db_row(log))

    @staticmethod
    def _to_db_row(log: LlmCallLogEntity) -> tuple[object, ...]:
        """Projects `log`'s insertable fields onto `_COLUMNS`, in table order."""
        return tuple(getattr(log, column) for column in _COLUMNS)
