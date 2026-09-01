import logging
from decimal import Decimal

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from commons.ai.observability import PydanticAILlmCallRecorder, TrackedCaller

_CALLER = TrackedCaller(
    caller="test_agent",
    model="openrouter/test-model",
    system_prompt="sys",
    expects_cost=True,
)


class _Out(BaseModel):
    value: str


def _run(text: str, cost: float | None = None):
    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        details = {"cost": cost} if cost is not None else None
        return ModelResponse(parts=[TextPart(content=text)], provider_details=details)

    return Agent(FunctionModel(_func), output_type=str).run_sync("prompt")


def test_records_success_fields() -> None:
    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(_run("risposta"))

    log = recorder.log
    assert log.caller == "test_agent"
    assert log.model == "openrouter/test-model"
    assert log.system_prompt == "sys"
    assert log.prompt == "prompt"
    assert log.response == "risposta"
    assert log.status == "success"
    assert log.error_message is None
    assert log.latency_ms is not None and log.latency_ms >= 0
    assert log.start_time is not None
    assert log.end_time is not None


def test_sums_reported_cost() -> None:
    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(_run("risposta", cost=0.000125))

    assert recorder.log.cost_usd == Decimal("0.000125")


def test_cost_is_none_when_provider_reports_nothing() -> None:
    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(_run("risposta"))

    assert recorder.log.cost_usd is None


def test_serializes_basemodel_output_as_json() -> None:
    agent = Agent(
        FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart(content='{"value": "x"}')])
        ),
        output_type=_Out,
    )

    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(agent.run_sync("prompt"))

    assert recorder.log.response == '{"value":"x"}'


def test_exception_marks_error_and_propagates() -> None:
    recorder = PydanticAILlmCallRecorder(_CALLER, "prompt")

    with pytest.raises(ValueError, match="boom"), recorder:
        raise ValueError("boom")

    assert recorder.log.status == "error"
    assert recorder.log.error_message == "boom"
    assert recorder.log.response is None


def test_logs_completion_info(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(_run("risposta"))

    assert "call completed" in caplog.text
    assert "test_agent" in caplog.text


def test_warns_when_cost_expected_but_absent(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    with PydanticAILlmCallRecorder(_CALLER, "prompt") as recorder:
        recorder.record(_run("risposta"))

    assert "reported no cost" in caplog.text


def test_no_cost_warning_when_not_expected(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    caller = _CALLER.model_copy(update={"expects_cost": False})

    with PydanticAILlmCallRecorder(caller, "prompt") as recorder:
        recorder.record(_run("risposta"))

    assert "reported no cost" not in caplog.text


def test_no_cost_warning_on_failed_call(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    recorder = PydanticAILlmCallRecorder(_CALLER, "prompt")

    with pytest.raises(ValueError), recorder:
        raise ValueError("boom")

    assert "reported no cost" not in caplog.text


def test_tracked_caller_is_frozen() -> None:
    with pytest.raises(Exception):
        _CALLER.caller = "other"  # pyright: ignore[reportAttributeAccessIssue]
