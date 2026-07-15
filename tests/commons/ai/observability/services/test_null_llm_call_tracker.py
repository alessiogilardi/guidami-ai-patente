from commons.ai.observability import NullLlmCallTracker
from domain.entities.observability import LlmCallLog


def _make_log() -> LlmCallLog:
    return LlmCallLog(
        caller="test_agent",
        model="openrouter/anthropic/claude-3.5-sonnet",
        prompt="Domanda.",
        response="Risposta.",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        latency_ms=42,
    )


def test_track_is_noop() -> None:
    tracker = NullLlmCallTracker()

    result = tracker.track(_make_log())

    assert result is None
