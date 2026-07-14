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
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.agents.dto.article_contextualizer import (
    ArticleContextualizerRequest,
    ArticleContextualizerResponse,
)

_PROVIDER = OpenRouterProvider(api_key="test-key")


@pytest.fixture
def agents_dir(tmp_path: Path) -> YamlRepository:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "article_contextualizer.yaml").write_text(
        "model_name: openrouter/google/gemini-2.5-flash-lite\n"
        "system: 'Test system.'\n"
        "user: 'Articolo: $title\\n$text\\n$paragraphs'\n",
        encoding="utf-8",
    )
    return YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(d))


def _request(**kwargs) -> ArticleContextualizerRequest:
    defaults = dict(title="Finalità", text="Comma 0.", paragraphs="1. Comma 1.\n2. Comma 2.")
    return ArticleContextualizerRequest(**{**defaults, **kwargs})


def test_run_sync_returns_article_contextualizer_response(agents_dir: YamlRepository) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir, _PROVIDER)
    expected_contexts = {"0": "Primo contesto.", "1": "Secondo contesto."}

    def func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"contexts": expected_contexts}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(func)):
        result = agent.run_sync(_request())

    assert isinstance(result, ArticleContextualizerResponse)
    assert result.contexts == {0: "Primo contesto.", 1: "Secondo contesto."}


def test_run_sync_passes_title_in_prompt(agents_dir: YamlRepository) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir, _PROVIDER)
    request = _request(title="Norme generali")
    captured_text: list[str] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        captured_text.append(part.content)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"contexts": {"0": "ctx"}}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request)

    assert any("Norme generali" in t for t in captured_text)


def test_run_sync_passes_paragraphs_in_prompt(agents_dir: YamlRepository) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir, _PROVIDER)
    request = _request(paragraphs="1. Primo comma.\n2. Secondo comma.")
    captured_text: list[str] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                        captured_text.append(part.content)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"contexts": {"0": "ctx"}}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request)

    assert any("Primo comma." in t for t in captured_text)
