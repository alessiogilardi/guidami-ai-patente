from decimal import Decimal

import pytest
from pydantic import ValidationError

from domain.entities.observability import LlmCallLog

_INSERTABLE_COLUMNS = {
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
}


def _log(**kwargs) -> LlmCallLog:
    defaults = dict(caller="image_description", model="gpt-4o-mini", prompt="Describe the sign.")
    return LlmCallLog(**{**defaults, **kwargs})


def test_llm_call_log_mirrors_table() -> None:
    """LlmCallLog is the insertable projection of llm_call_logs: no id, no created_at."""
    fields = set(LlmCallLog.model_fields)

    assert "id" not in fields
    assert "created_at" not in fields
    assert fields == _INSERTABLE_COLUMNS


def test_defaults() -> None:
    """A minimal instance defaults status to success and leaves optional fields unset."""
    log = _log()

    assert log.status == "success"
    assert log.system_prompt is None
    assert log.response is None
    assert log.input_tokens is None
    assert log.output_tokens is None
    assert log.total_tokens is None
    assert log.cost_usd is None
    assert log.error_message is None
    assert log.latency_ms is None
    assert log.start_time is None
    assert log.end_time is None


def test_cost_is_decimal() -> None:
    """cost_usd accepts a Decimal and rejects a non-numeric string."""
    log = _log(cost_usd=Decimal("0.001234"))
    assert log.cost_usd == Decimal("0.001234")

    with pytest.raises(ValidationError):
        _log(cost_usd="not-a-number")
