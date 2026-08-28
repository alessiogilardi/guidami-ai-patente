from collections.abc import Iterator
from decimal import Decimal

import pytest
from psycopg import sql

from commons.ai.observability import LlmCallLogEntity, LlmCallLogRepository
from commons.clients import PostgresClient
from commons.configs import PostgresConnectionConfig


@pytest.fixture
def client(postgres_test_config: PostgresConnectionConfig) -> Iterator[PostgresClient]:
    with PostgresClient(postgres_test_config) as client:
        client.truncate("llm_call_logs")
        yield client
        client.truncate("llm_call_logs")


@pytest.mark.integration
def test_insert_round_trip(client: PostgresClient) -> None:
    repository = LlmCallLogRepository(client)
    success_log = LlmCallLogEntity(
        caller="road_sign_describer",
        model="openrouter/anthropic/claude-3.5-sonnet",
        system_prompt="Sistema.",
        prompt="Domanda.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=Decimal("0.001234"),
        status="success",
        latency_ms=120,
    )
    error_log = LlmCallLogEntity(
        caller="article_contextualizer",
        model="openrouter/anthropic/claude-3.5-sonnet",
        prompt="Domanda fallita.",
        status="error",
        error_message="timeout",
    )

    repository.insert(success_log)
    repository.insert(error_log)

    rows = client.fetch(
        sql.SQL("SELECT caller, cost_usd, status, error_message FROM llm_call_logs ORDER BY id")
    )
    assert rows == [
        ("road_sign_describer", Decimal("0.001234"), "success", None),
        ("article_contextualizer", None, "error", "timeout"),
    ]
