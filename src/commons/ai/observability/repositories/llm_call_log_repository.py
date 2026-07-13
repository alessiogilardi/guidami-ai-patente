from psycopg import sql

from commons.clients import PostgresClient
from domain.entities.observability import LlmCallLog

# Insertable columns of `llm_call_logs`, in table order (see db/init.sql). `id` and
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

_INSERT_QUERY = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders})").format(
    table=sql.Identifier("llm_call_logs"),
    columns=sql.SQL(", ").join(sql.Identifier(column) for column in _COLUMNS),
    placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in _COLUMNS),
)


class LlmCallLogRepository:
    """Append-only repository for `llm_call_logs`.

    Commons-level (unlike the ingestor's `*StoreRepository`s): the future FastAPI
    app will track calls too. Does not extend `BulkInsertStoreRepository` — its
    truncate + bulk-reload contract does not fit an append-only log.
    """

    def __init__(self, client: PostgresClient) -> None:
        """Stores the DB client used to persist call logs."""
        self._client = client

    def insert(self, log: LlmCallLog) -> None:
        """Inserts one `LlmCallLog` row. `Decimal` adapts to `NUMERIC` natively."""
        self._client.execute(_INSERT_QUERY, self._to_db_row(log))

    @staticmethod
    def _to_db_row(log: LlmCallLog) -> tuple[object, ...]:
        """Projects `log`'s insertable fields onto `_COLUMNS`, in table order."""
        return tuple(getattr(log, column) for column in _COLUMNS)
