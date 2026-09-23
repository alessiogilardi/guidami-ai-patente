"""Tests for ExplanationWriterAgent's output_validator (ordinal-citation grounding)."""

import logging
from dataclasses import dataclass

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from guidami_ai_patente.agents import ExplanationWriterAgent
from guidami_ai_patente.agents.explanation_writer.dto import ExplanationWriterRequest
from guidami_ai_patente.models import LabeledComma

_PROVIDER = OpenRouterProvider(api_key="test-key")

_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Quiz: $quiz_text",
    num_retries=3,
)


@dataclass
class _AgentConfigRepositoryDouble:
    config: AgentConfig

    def load(self, name: str) -> AgentConfig:
        return self.config


@dataclass
class _OpenRouterProviderComponentDouble:
    provider: OpenRouterProvider


@dataclass
class _LlmCallTrackerProviderDouble:
    tracker: None = None


def _make_agent() -> ExplanationWriterAgent:
    """Builds the agent the way pywire does: Autowired fields set, then __init__ runs.

    Bypasses the container so this test needs no DB/HTTP fixtures, while still
    exercising the real `ExplanationWriterAgent.__init__` (ADR 0023's field-then-init
    ordering) — including the output_validator registration under test.
    """
    agent = object.__new__(ExplanationWriterAgent)
    agent.agent_configs = _AgentConfigRepositoryDouble(_TEST_CONFIG)  # type: ignore[assignment]
    agent.open_router = _OpenRouterProviderComponentDouble(_PROVIDER)  # type: ignore[assignment]
    agent.tracker_provider = _LlmCallTrackerProviderDouble()  # type: ignore[assignment]
    agent.__init__()  # type: ignore[misc]
    return agent


def _make_request(comma_count: int) -> ExplanationWriterRequest:
    commas = [
        LabeledComma(
            source="cds",
            article_number="157",
            article_title="Sosta",
            comma_number=str(i),
            text=f"Testo {i}.",
            judge_rank=i,
        )
        for i in range(1, comma_count + 1)
    ]
    return ExplanationWriterRequest(
        quiz_text="Domanda di prova.", correct_answer=True, commas=commas
    )


def _sequenced_model(responses: list[list[int]]) -> FunctionModel:
    """Returns one scripted cited_comma_numbers list per call, in order."""
    calls = {"n": 0}

    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        assert info.output_tools
        tool_name = info.output_tools[0].name
        cited = responses[calls["n"] - 1]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name,
                    {"explanation": "Spiegazione di prova.", "cited_comma_numbers": cited},
                )
            ]
        )

    return FunctionModel(_func)


async def test_an_out_of_range_ordinal_self_corrects_on_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    agent = _make_agent()
    request = _make_request(comma_count=2)

    with agent.core_agent.override(model=_sequenced_model([[9], [1]])):
        response = await agent.run(request)

    assert response.cited_comma_numbers == [1]
    assert "out-of-range" in caplog.text


async def test_an_ordinal_that_never_self_corrects_raises_unexpected_model_behavior() -> None:
    """With num_retries=3, 4 total attempts are allowed before pydantic_ai gives up."""
    agent = _make_agent()
    request = _make_request(comma_count=2)

    with (
        agent.core_agent.override(model=_sequenced_model([[9], [9], [9], [9]])),
        pytest.raises(UnexpectedModelBehavior, match="Exceeded maximum output retries"),
    ):
        await agent.run(request)
