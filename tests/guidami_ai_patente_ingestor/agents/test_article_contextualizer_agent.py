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

from guidami_ai_patente_ingestor.agents import ArticleContextualizerAgent
from guidami_ai_patente_ingestor.entities import Article


def _article(repealed: bool = False) -> Article:
    return Article(
        number="1",
        title="Finalità",
        text="Comma 0.",
        paragraphs=["Comma 1.", "Comma 2."],
        url="https://example.com/art-1",
        scraped_at="2025-01-01T00:00:00",
        repealed=repealed,
    )


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "article_contextualizer.yaml").write_text(
        "model_name: openrouter/google/gemini-2.5-flash-lite\n"
        "system: 'Test system.'\n"
        "user: 'Articolo: $title\\n$text\\n$paragraphs'\n",
        encoding="utf-8",
    )
    return d


def test_contextualize_returns_dict_for_article(agents_dir: Path) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir)
    expected = {"0": "Primo contesto.", "1": "Secondo contesto."}

    def func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"response": expected}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(func)):
        result = agent.contextualize(_article())

    assert result == {0: "Primo contesto.", 1: "Secondo contesto."}


def test_contextualize_skips_repealed_and_returns_empty(agents_dir: Path) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir)
    model_was_called = False

    def flagging_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal model_was_called
        model_was_called = True
        return ModelResponse(parts=[])

    with agent.core_agent.override(model=FunctionModel(flagging_func)):
        result = agent.contextualize(_article(repealed=True))

    assert result == {}
    assert not model_was_called


def test_contextualize_passes_article_title_in_prompt(agents_dir: Path) -> None:
    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", agents_dir)
    article = _article()
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
                    args=json.dumps({"response": {"0": "ctx"}}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.contextualize(article)

    assert any(article.title in t for t in captured_text)
