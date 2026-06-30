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

from guidami_ai_patente_ingestor.agents import RoadSignDescriberAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    d = tmp_path / "agents"
    d.mkdir()
    (d / "road_sign_describer.yaml").write_text(
        "model_name: openrouter/google/gemini-2.5-flash-lite\n"
        "system: 'Test system.'\n"
        "user: 'Argomento: $topic\\nDomanda: $text\\nDescrivi il segnale.'\n",
        encoding="utf-8",
    )
    return d


def test_run_sync_returns_road_sign_describer_response(agents_dir: Path, tmp_path: Path) -> None:
    img = tmp_path / "stop.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(topic="Segnaletica", text="Cosa indica il segnale?")

    agent = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_dir)
    with agent.core_agent.override(
        model=TestModel(custom_output_args={"name": "Stop", "description": "Segnale rosso."})
    ):
        result = agent.run_sync(request, images=(img,))

    assert isinstance(result, RoadSignDescriberResponse)
    assert result.name == "Stop"
    assert result.description == "Segnale rosso."


def test_run_sync_sends_binary_content(agents_dir: Path, tmp_path: Path) -> None:
    img = tmp_path / "stop.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(topic="Segnaletica", text="Domanda.")

    agent = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_dir)
    captured: list[ModelMessage] = []

    def capturing_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.extend(messages)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    tool_call_id="call_1",
                    args=json.dumps({"name": "Stop", "description": "desc"}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request, images=(img,))

    has_binary = any(
        isinstance(part, UserPromptPart)
        and isinstance(part.content, list)
        and any(isinstance(c, BinaryContent) for c in part.content)
        for msg in captured
        if isinstance(msg, ModelRequest)
        for part in msg.parts
    )
    assert has_binary


def test_run_sync_passes_topic_in_prompt(agents_dir: Path, tmp_path: Path) -> None:
    img = tmp_path / "stop.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(topic="Precedenza", text="Domanda sul segnale.")

    agent = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_dir)
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
                    args=json.dumps({"name": "Precedenza", "description": "desc"}),
                )
            ]
        )

    with agent.core_agent.override(model=FunctionModel(capturing_func)):
        agent.run_sync(request, images=(img,))

    assert any("Precedenza" in t for t in captured_text)


def test_render_prompt_with_image_includes_binary_content(
    agents_dir: Path, tmp_path: Path
) -> None:
    img = tmp_path / "stop.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    request = RoadSignDescriberRequest(topic="Segnaletica", text="Domanda di test.")

    agent = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_dir)
    parts = agent.renderer.render(request, images=(img,))

    assert isinstance(parts, list)
    assert any(isinstance(p, BinaryContent) for p in parts)
