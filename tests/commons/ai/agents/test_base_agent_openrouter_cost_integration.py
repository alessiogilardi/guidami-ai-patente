import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig, BaseAgent
from commons.ai.observability import LlmCallLogEntity, PydanticAILlmCallRecorder, TrackedCaller


class _ListTracker:
    """Fake LlmCallTracker collecting every tracked log in memory."""

    def __init__(self) -> None:
        self.logs: list[LlmCallLogEntity] = []

    @contextmanager
    def track(
        self, tracked_caller: TrackedCaller, prompt: str
    ) -> Iterator[PydanticAILlmCallRecorder]:
        recorder = PydanticAILlmCallRecorder(tracked_caller, prompt)
        try:
            with recorder:
                yield recorder
        finally:
            self.logs.append(recorder.log)


class _StrAgent(BaseAgent[str, str]):
    output_type = str


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="requires OPENROUTER_API_KEY to call the real OpenRouter endpoint",
)
def test_real_agent_call_persists_nonnull_cost() -> None:
    config = AgentConfig(
        model_name="openrouter/google/gemini-2.5-flash-lite",
        system="Rispondi con una sola parola.",
        user="Scrivi la parola: ciao",
    )
    provider = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
    tracker = _ListTracker()
    agent = _StrAgent(config, provider, tracker=tracker)

    agent.run_sync("")

    assert len(tracker.logs) == 1
    log = tracker.logs[0]
    assert log.cost_usd is not None
    assert log.cost_usd > 0
