from datetime import UTC, datetime

from commons.ai.observability.mappers import LlmCallLogMapper
from commons.ai.observability.models import LlmCallCaptureModel

_MODEL = "openrouter/anthropic/claude-3.5-sonnet"


def test_from_model_to_entity_maps_all_fields() -> None:
    data = LlmCallCaptureModel(
        caller="test_agent",
        model=_MODEL,
        prompt="Domanda.",
        system_prompt="Sistema.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        status="success",
        error_message=None,
        latency_ms=42,
        start_time=datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 7, 13, 10, 0, 1, tzinfo=UTC),
    )

    log = LlmCallLogMapper.from_model_to_entity(data)

    assert log.caller == data.caller
    assert log.model == data.model
    assert log.prompt == data.prompt
    assert log.system_prompt == data.system_prompt
    assert log.response == data.response
    assert log.input_tokens == data.input_tokens
    assert log.output_tokens == data.output_tokens
    assert log.total_tokens == data.total_tokens
    assert log.status == data.status
    assert log.error_message == data.error_message
    assert log.latency_ms == data.latency_ms
    assert log.start_time == data.start_time
    assert log.end_time == data.end_time
    assert log.cost_usd is None


def test_from_model_to_entity_error_path() -> None:
    data = LlmCallCaptureModel(
        caller="test_agent",
        model=_MODEL,
        prompt="Domanda.",
        system_prompt=None,
        response=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        status="error",
        error_message="boom",
        latency_ms=7,
        start_time=datetime(2026, 7, 13, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 7, 13, 10, 0, 1, tzinfo=UTC),
    )

    log = LlmCallLogMapper.from_model_to_entity(data)

    assert log.status == "error"
    assert log.error_message == "boom"
    assert log.response is None
