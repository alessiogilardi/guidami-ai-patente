"""Tests for QuestionExplainerAgent's output_validator (FR-6, AD-8)."""

import logging
from dataclasses import dataclass

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from guidami_ai_patente.agents import QuestionExplainerAgent
from guidami_ai_patente.agents.question_explainer.dto import QuestionExplainerRequest
from guidami_ai_patente.models import GlossaryCandidate

_PROVIDER = OpenRouterProvider(api_key="test-key")

_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Domanda: $text",
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


def _make_agent() -> QuestionExplainerAgent:
    agent = object.__new__(QuestionExplainerAgent)
    agent.agent_configs = _AgentConfigRepositoryDouble(_TEST_CONFIG)  # type: ignore[assignment]
    agent.open_router = _OpenRouterProviderComponentDouble(_PROVIDER)  # type: ignore[assignment]
    agent.tracker_provider = _LlmCallTrackerProviderDouble()  # type: ignore[assignment]
    agent.__init__()  # type: ignore[misc]
    return agent


def _make_request(candidate_count: int) -> QuestionExplainerRequest:
    candidates = [
        GlossaryCandidate(
            term=f"termine{i}",
            definition=f"Definizione {i}.",
            term_ru="x",
        )
        for i in range(1, candidate_count + 1)
    ]
    return QuestionExplainerRequest(text="Domanda di prova.", candidates=candidates)


def _sequenced_model(responses: list[list[int]]) -> FunctionModel:
    calls = {"n": 0}

    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        assert info.output_tools
        tool_name = info.output_tools[0].name
        cited = responses[calls["n"] - 1]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name, {"explanation": "Spiegazione.", "cited_term_numbers": cited}
                )
            ]
        )

    return FunctionModel(_func)


async def test_an_out_of_range_ordinal_self_corrects_on_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    agent = _make_agent()
    request = _make_request(candidate_count=2)

    with agent.core_agent.override(model=_sequenced_model([[9], [1]])):
        response = await agent.run(request)

    assert response.cited_term_numbers == [1]
    assert "out-of-range" in caplog.text


async def test_an_ordinal_that_never_self_corrects_raises_unexpected_model_behavior() -> None:
    agent = _make_agent()
    request = _make_request(candidate_count=2)

    with (
        agent.core_agent.override(model=_sequenced_model([[9], [9], [9], [9]])),
        pytest.raises(UnexpectedModelBehavior, match="Exceeded maximum output retries"),
    ):
        await agent.run(request)


async def test_zero_candidates_is_accepted_without_a_validator_error() -> None:
    """FR-4/FR-6: an empty candidate list is valid — the agent must still run."""
    agent = _make_agent()
    request = _make_request(candidate_count=0)

    with agent.core_agent.override(model=_sequenced_model([[]])):
        response = await agent.run(request)

    assert response.cited_term_numbers == []
