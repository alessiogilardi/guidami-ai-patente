"""Tests for RetrievalJudgeAgent."""

import json
from pathlib import Path

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from domain.models.retrieval import RetrievedComma
from retrieval_evaluation.agents import RetrievalJudgeAgent
from retrieval_evaluation.agents.retrieval_judge.dto import (
    RetrievalJudgeRequest,
    RetrievalJudgeResponse,
)

_PROVIDER = OpenRouterProvider(api_key="test-key")


@pytest.fixture
def agents_dir(tmp_path: Path) -> YamlRepository:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "retrieval_judge.yaml").write_text(
        "model_name: openrouter/google/gemini-2.5-flash-lite\n"
        "system: 'Test system.'\n"
        "user: 'Domanda: $quiz_text\\nRisposta: $correct_answer_it\\n$commas_block'\n",
        encoding="utf-8",
    )
    return YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(d))


def _make_request() -> RetrievalJudgeRequest:
    return RetrievalJudgeRequest(
        quiz_text="Il segnale indica obbligo di fermata.",
        correct_answer=True,
        commas=[
            RetrievedComma(
                source="cds",
                article_number="41",
                article_title="Segnali di pericolo",
                comma_number="1",
                text="Il segnale di stop impone l'obbligo di arresto.",
                distance=0.05,
            )
        ],
    )


def test_run_sync_returns_retrieval_judge_response(agents_dir: YamlRepository) -> None:
    agent = RetrievalJudgeAgent.from_yaml("retrieval_judge", agents_dir, _PROVIDER)

    with agent.core_agent.override(
        model=TestModel(custom_output_args={"is_clear": True, "rationale": "Il comma è chiaro."})
    ):
        result = agent.run_sync(_make_request())

    assert isinstance(result, RetrievalJudgeResponse)
    assert result.is_clear is True
    assert result.rationale == "Il comma è chiaro."


def test_run_sync_includes_quiz_text_and_comma_citation_in_prompt(
    agents_dir: YamlRepository,
) -> None:
    agent = RetrievalJudgeAgent.from_yaml("retrieval_judge", agents_dir, _PROVIDER)
    captured: list[ModelMessage] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.extend(messages)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"is_clear": True, "rationale": "Chiaro."}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(_make_request())

    prompt_texts = [
        part.content
        for msg in captured
        if isinstance(msg, ModelRequest)
        for part in msg.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]
    assert any("obbligo di fermata" in text for text in prompt_texts)
    assert any("cds art. 41 c. 1" in text for text in prompt_texts)
