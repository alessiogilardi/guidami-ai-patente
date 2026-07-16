import json
from pathlib import Path

import pytest
from pydantic_ai import BinaryContent
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
from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    QuizContextModel,
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)

_PROVIDER = OpenRouterProvider(api_key="test-key")


@pytest.fixture
def agents_dir(tmp_path: Path) -> YamlRepository:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "road_sign_describer.yaml").write_text(
        "model_name: openrouter/google/gemini-2.5-flash-lite\n"
        "system: 'Test system.'\n"
        "user: '$contexts_block\\nDescrivi il segnale.'\n",
        encoding="utf-8",
    )
    return YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(d))


def test_run_sync_returns_road_sign_describer_response(
    agents_dir: YamlRepository, tmp_path: Path
) -> None:
    (tmp_path / "stop.jpg").write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="Segnaletica", texts=["Cosa indica il segnale?"])]
    )

    agent = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_dir, _PROVIDER, LocalFileSystemClient(tmp_path)
    )
    with agent.core_agent.override(
        model=TestModel(
            custom_output_args={
                "visual_analysis": "Segnale triangolare rosso con bordo bianco, forma ottagonale.",
                "name": "Stop",
                "description": "Segnale rosso.",
            }
        )
    ):
        result = agent.run_sync(request, images=(Path("stop.jpg"),))

    assert isinstance(result, RoadSignDescriberResponse)
    assert (
        result.visual_analysis == "Segnale triangolare rosso con bordo bianco, forma ottagonale."
    )
    assert result.name == "Stop"
    assert result.description == "Segnale rosso."


def test_run_sync_sends_binary_content(agents_dir: YamlRepository, tmp_path: Path) -> None:
    (tmp_path / "stop.jpg").write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="Segnaletica", texts=["Domanda."])]
    )

    agent = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_dir, _PROVIDER, LocalFileSystemClient(tmp_path)
    )
    captured: list[ModelMessage] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.extend(messages)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps(
                        {"visual_analysis": "analisi", "name": "Stop", "description": "desc"}
                    ),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request, images=(Path("stop.jpg"),))

    has_binary = any(
        isinstance(part, UserPromptPart)
        and isinstance(part.content, list)
        and any(isinstance(c, BinaryContent) for c in part.content)
        for msg in captured
        if isinstance(msg, ModelRequest)
        for part in msg.parts
    )
    assert has_binary


def test_run_sync_passes_topic_in_prompt(agents_dir: YamlRepository, tmp_path: Path) -> None:
    (tmp_path / "stop.jpg").write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="Precedenza", texts=["Domanda sul segnale."])]
    )

    agent = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_dir, _PROVIDER, LocalFileSystemClient(tmp_path)
    )
    captured_text: list[str] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for msg in messages:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                        for c in part.content:
                            if isinstance(c, str):
                                captured_text.append(c)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps(
                        {"visual_analysis": "analisi", "name": "Precedenza", "description": "desc"}
                    ),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request, images=(Path("stop.jpg"),))

    assert any("Precedenza" in t for t in captured_text)


def test_render_prompt_with_image_includes_binary_content(
    agents_dir: YamlRepository, tmp_path: Path
) -> None:
    (tmp_path / "stop.jpg").write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(
        contexts=[QuizContextModel(topic="Segnaletica", texts=["Domanda di test."])]
    )

    agent = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer", agents_dir, _PROVIDER, LocalFileSystemClient(tmp_path)
    )
    parts = agent._renderer.render(request, images=(Path("stop.jpg"),))

    assert isinstance(parts, list)
    assert any(isinstance(p, BinaryContent) for p in parts)
