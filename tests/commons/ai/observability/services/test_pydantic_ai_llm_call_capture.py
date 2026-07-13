import pytest
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.run import AgentRunResult
from pydantic_ai.usage import RunUsage

from commons.ai.observability import PydanticAILlmCallCapture
from domain.entities.observability import LlmCallLog

_MODEL = "openrouter/anthropic/claude-3.5-sonnet"


class _FakeTracker:
    """Collects tracked logs in memory, in `track()` call order."""

    def __init__(self) -> None:
        self.tracked: list[LlmCallLog] = []

    def track(self, log: LlmCallLog) -> None:
        self.tracked.append(log)


def test_success_path() -> None:
    capture = PydanticAILlmCallCapture(
        caller="test_agent",
        model=_MODEL,
        prompt="Domanda di test.",
        system_prompt="Sistema di test.",
    )

    with capture:
        capture.record(_make_result("Risposta di test.", input_tokens=10, output_tokens=5))

    log = capture.log
    assert log.caller == "test_agent"
    assert log.model == _MODEL
    assert log.status == "success"
    assert log.response == "Risposta di test."
    assert log.input_tokens == 10
    assert log.output_tokens == 5
    assert log.total_tokens == 15
    assert log.latency_ms is not None
    assert log.latency_ms >= 0
    assert log.cost_usd is None
    assert log.error_message is None
    assert log.start_time is not None
    assert log.end_time is not None
    assert log.end_time >= log.start_time


def test_error_path_propagates_and_records() -> None:
    capture = PydanticAILlmCallCapture(
        caller="test_agent",
        model=_MODEL,
        prompt="Domanda di test.",
        system_prompt=None,
    )

    with pytest.raises(RuntimeError, match="boom"), capture:
        raise RuntimeError("boom")

    log = capture.log
    assert log.status == "error"
    assert log.error_message is not None
    assert "boom" in log.error_message
    assert log.input_tokens is None
    assert log.output_tokens is None
    assert log.response is None
    assert log.latency_ms is not None
    assert log.latency_ms >= 0
    assert log.start_time is not None
    assert log.end_time is not None
    assert log.end_time >= log.start_time


def test_tracked_persists_log_on_success() -> None:
    tracker = _FakeTracker()

    with PydanticAILlmCallCapture.tracked(
        "test_agent", _MODEL, "Domanda.", "Sistema.", tracker
    ) as capture:
        capture.record(_make_result("Risposta.", input_tokens=10, output_tokens=5))

    assert len(tracker.tracked) == 1
    assert tracker.tracked[0].status == "success"
    assert tracker.tracked[0].response == "Risposta."


def test_tracked_persists_log_on_error() -> None:
    tracker = _FakeTracker()

    with (
        pytest.raises(RuntimeError, match="boom"),
        PydanticAILlmCallCapture.tracked("test_agent", _MODEL, "Domanda.", None, tracker),
    ):
        raise RuntimeError("boom")

    assert len(tracker.tracked) == 1
    assert tracker.tracked[0].status == "error"
    assert tracker.tracked[0].error_message is not None
    assert "boom" in tracker.tracked[0].error_message


def _make_result(output: str, *, input_tokens: int, output_tokens: int) -> AgentRunResult[str]:
    usage = RunUsage(input_tokens=input_tokens, output_tokens=output_tokens)
    return AgentRunResult(output=output, _state=GraphAgentState(usage=usage))
