from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from psycopg import sql

from commons.ai.observability import LlmCallLogEntity
from commons.ai.observability.repositories.postgres_llm_call_log_repository import (
    _COLUMNS,
    PostgresLlmCallLogRepository,
)
from commons.clients import PostgresClient


class _RecordingClient(PostgresClient):
    """Fake `PostgresClient` recording every query and its params.

    Deliberately skips `super().__init__()` — a real `PostgresClient` opens a live DB
    connection, which this unit test must not do.
    """

    def __init__(self) -> None:
        self.queries: list[sql.SQL | sql.Composed] = []
        self.params: list[Sequence[object] | None] = []

    def execute(
        self, query: sql.SQL | sql.Composed, params: Sequence[object] | None = None
    ) -> None:
        self.queries.append(query)
        self.params.append(params)


def test_columns_matches_insertable_table_columns() -> None:
    assert _COLUMNS == (
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


def test_to_db_row_projects_log_fields_in_column_order() -> None:
    log = LlmCallLogEntity(
        caller="road_sign_describer",
        model="openrouter/anthropic/claude-3.5-sonnet",
        system_prompt="Sistema.",
        prompt="Domanda.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=Decimal("0.000123"),
        status="success",
        error_message=None,
        latency_ms=42,
        start_time=datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 7, 13, 10, 0, 1, tzinfo=UTC),
    )

    row = PostgresLlmCallLogRepository._to_db_row(log)

    assert row == tuple(getattr(log, column) for column in _COLUMNS)


def test_insert_targets_the_configured_table() -> None:
    client = _RecordingClient()
    repository = PostgresLlmCallLogRepository("custom_logs", client)

    repository.insert(LlmCallLogEntity(caller="c", model="m", prompt="p"))

    assert "custom_logs" in client.queries[0].as_string(None)
