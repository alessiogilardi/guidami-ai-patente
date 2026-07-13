from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from commons.agents import BaseAgent
from commons.agents.utils.prompt_renderer import PromptRenderer
from commons.clients.file_system import LocalFileSystemClient
from commons.configs import AgentConfig
from commons.repositories import YamlRepository
from domain.entities.observability import LlmCallLog


def _write_yaml(agents_dir: Path, name: str, content: dict) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.yaml").write_text(yaml.dump(content), encoding="utf-8")


MINIMAL_CONFIG: dict = {
    "model_name": "openrouter/google/gemini-2.5-flash-lite",
    "system": "Sistema di test.",
    "user": "Testo: $input",
}


class _StrAgent(BaseAgent[str, str]):
    output_type = str


# --- YamlRepository (agent config loading) ---


def test_yaml_repository_raises_file_not_found_for_missing_yaml(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    repo = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))
    with pytest.raises(FileNotFoundError, match="nonexistent.yaml"):
        repo.load("nonexistent.yaml")


def test_yaml_repository_parses_yaml_into_agent_config(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    repo = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))
    config = repo.load("test_agent.yaml")
    assert isinstance(config, AgentConfig)
    assert config.model_name == "openrouter/google/gemini-2.5-flash-lite"


# --- PromptRenderer ---


def test_prompt_renderer_substitutes_variables() -> None:
    renderer = PromptRenderer("Testo: $input")
    result = renderer.render({"input": "ciao"})
    assert result == "Testo: ciao"


def test_prompt_renderer_returns_list_with_binary_content_for_images(
    tmp_path: Path,
) -> None:
    (tmp_path / "stop.jpg").write_bytes(b"\xff\xd8\xff")
    renderer = PromptRenderer("Descrivi.", LocalFileSystemClient(tmp_path))
    parts = renderer.render({}, images=(Path("stop.jpg"),))
    assert isinstance(parts, list)
    assert any(isinstance(p, BinaryContent) for p in parts)


def test_prompt_renderer_raises_value_error_when_no_file_reader_configured() -> None:
    renderer = PromptRenderer("Descrivi.")
    with pytest.raises(ValueError, match="file_reader"):
        renderer.render({}, images=(Path("x.jpg"),))


def test_prompt_renderer_renders_dataclass() -> None:
    @dataclass
    class Foo:
        input: str

    renderer = PromptRenderer("Testo: $input")
    result = renderer.render(Foo(input="ciao"))
    assert result == "Testo: ciao"


def test_prompt_renderer_renders_str_directly() -> None:
    renderer = PromptRenderer("Testo: $input")
    result = renderer.render("Prompt pre-renderizzato")
    assert result == "Prompt pre-renderizzato"


# --- BaseAgent ---


def test_base_agent_created_from_valid_config(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    repo = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))
    config = repo.load("test_agent.yaml")
    agent = _StrAgent(config)
    assert agent is not None


def test_base_agent_from_yaml_factory_method(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    agent = _StrAgent.from_yaml(
        "test_agent",
        YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)),
    )
    assert agent is not None


def test_base_agent_from_yaml_raises_file_not_found(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        _StrAgent.from_yaml(
            "nonexistent",
            YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)),
        )


def test_base_agent_yaml_params_mapped_to_model_settings(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(
        agents_dir,
        "test_agent",
        {
            "model_name": "openrouter/google/gemini-2.5-flash-lite",
            "temperature": 0.5,
            "max_tokens": 256,
            "timeout": 30.0,
            "num_retries": 2,
            "system": "Sys.",
            "user": "User.",
        },
    )
    agent = _StrAgent.from_yaml(
        "test_agent",
        YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)),
    )
    assert agent.core_agent.model_settings["temperature"] == 0.5
    assert agent.core_agent.model_settings["max_tokens"] == 256
    assert agent.core_agent._max_output_retries == 2


def test_base_agent_model_name_slash_converted_to_colon(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    # Should not raise even without OPENROUTER_API_KEY (defer_model_check=True)
    agent = _StrAgent.from_yaml(
        "test_agent",
        YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir)),
    )
    assert agent is not None


# --- BaseAgent tracking (LlmCallTracker injection) ---


class _ListTracker:
    """Fake LlmCallTracker collecting every tracked log in memory."""

    def __init__(self) -> None:
        self.logs: list[LlmCallLog] = []

    def track(self, log: LlmCallLog) -> None:
        self.logs.append(log)


def _respond(text: str):
    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=text)])

    return _func


def _fail(exc: Exception):
    def _func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise exc

    return _func


def _load_agent(tmp_path: Path, tracker: _ListTracker | None = None) -> BaseAgent[str, str]:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    repo = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))
    config = repo.load("test_agent.yaml")
    return _StrAgent(config, tracker=tracker)


def test_tracked_run_sync_records_success(tmp_path: Path) -> None:
    tracker = _ListTracker()
    agent = _load_agent(tmp_path, tracker=tracker)

    with agent.core_agent.override(model=FunctionModel(_respond("Risposta di test."))):
        output = agent.run_sync("Ciao")

    assert output == "Risposta di test."
    assert len(tracker.logs) == 1
    log = tracker.logs[0]
    assert log.caller == "_StrAgent"
    assert log.model == MINIMAL_CONFIG["model_name"]
    assert log.prompt == "Ciao"
    assert log.response == "Risposta di test."
    assert log.status == "success"


async def test_tracked_run_records_success(tmp_path: Path) -> None:
    tracker = _ListTracker()
    agent = _load_agent(tmp_path, tracker=tracker)

    with agent.core_agent.override(model=FunctionModel(_respond("Risposta async."))):
        output = await agent.run("Ciao async")

    assert output == "Risposta async."
    assert len(tracker.logs) == 1
    log = tracker.logs[0]
    assert log.response == "Risposta async."
    assert log.status == "success"


def test_tracked_error_propagates_and_logs(tmp_path: Path) -> None:
    tracker = _ListTracker()
    agent = _load_agent(tmp_path, tracker=tracker)

    with (
        agent.core_agent.override(model=FunctionModel(_fail(ValueError("boom")))),
        pytest.raises(ValueError, match="boom"),
    ):
        agent.run_sync("Ciao")

    assert len(tracker.logs) == 1
    assert tracker.logs[0].status == "error"


def test_untracked_agent_unchanged(tmp_path: Path) -> None:
    agent = _load_agent(tmp_path, tracker=None)

    with agent.core_agent.override(model=FunctionModel(_respond("ok"))):
        output = agent.run_sync("Ciao")

    assert output == "ok"


def test_repr(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    repo = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))
    config = repo.load("test_agent.yaml")

    agent = _StrAgent(config, name="custom_name")

    assert repr(agent) == "_StrAgent(name='custom_name')"
