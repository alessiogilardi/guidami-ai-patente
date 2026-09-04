"""Tests for CommaLabelerAgent's output_validator (spec 0014, FR-3)."""

import logging

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from domain.models.retrieval import RetrievedComma
from labeling.agents import CommaLabelerAgent
from labeling.agents.comma_labeler.dto import CommaLabelerRequest

_PROVIDER = OpenRouterProvider(api_key="test-key")

_TEST_CONFIG = AgentConfig(
    model_name="openrouter/google/gemini-2.5-flash-lite",
    system="Sistema di test.",
    user="Quiz: $quiz_text",
    num_retries=3,
)


def _make_request(candidate_count: int) -> CommaLabelerRequest:
    candidates = [
        RetrievedComma(
            id=i,
            source="cds",
            article_number="41",
            article_title="Segnali di pericolo",
            comma_number="1",
            text=f"Testo {i}.",
            distance=0.1,
        )
        for i in range(1, candidate_count + 1)
    ]
    return CommaLabelerRequest(
        quiz_text="Domanda di prova.", correct_answer=True, candidates=candidates
    )


def _sequenced_model(responses: list[list[int]]) -> FunctionModel:
    """Returns one scripted comma_numbers list per call, in order."""
    calls = {"n": 0}

    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        assert info.output_tools
        tool_name = info.output_tools[0].name
        comma_numbers = responses[calls["n"] - 1]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name, {"comma_numbers": comma_numbers, "rationale": "Motivazione."}
                )
            ]
        )

    return FunctionModel(_func)


async def test_an_out_of_range_ordinal_self_corrects_on_retry(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    agent = CommaLabelerAgent(_TEST_CONFIG, _PROVIDER)
    request = _make_request(candidate_count=2)

    with agent.core_agent.override(model=_sequenced_model([[9], [1]])):
        response = await agent.run(request)

    assert response.comma_numbers == [1]
    assert "out-of-range" in caplog.text


async def test_an_ordinal_that_never_self_corrects_raises_unexpected_model_behavior() -> None:
    """Validates retry behavior on ordinals that never self-correct.

    With num_retries=3, 4 total attempts are allowed. pydantic_ai counts failed
    attempts and raises UnexpectedModelBehavior once the retry budget is exceeded.
    """
    agent = CommaLabelerAgent(_TEST_CONFIG, _PROVIDER)
    request = _make_request(candidate_count=2)

    with (
        agent.core_agent.override(model=_sequenced_model([[9], [9], [9], [9]])),
        pytest.raises(UnexpectedModelBehavior, match="Exceeded maximum output retries"),
    ):
        await agent.run(request)
