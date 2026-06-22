from pathlib import Path

import pytest
import yaml
from pydantic_ai import BinaryContent

from commons.agents import BaseAgent
from commons.agents.base_agent import ConfigLoader, PromptRenderer
from commons.configs import AgentConfig


def _write_yaml(agents_dir: Path, name: str, content: dict) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.yaml").write_text(yaml.dump(content), encoding="utf-8")


MINIMAL_CONFIG: dict = {
    "model_name": "openrouter/google/gemini-2.5-flash-lite",
    "system": "Sistema di test.",
    "user": "Testo: $input",
}


# --- ConfigLoader ---


def test_config_loader_raises_file_not_found_for_missing_yaml(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        ConfigLoader.from_yaml(agents_dir, "nonexistent")


def test_config_loader_parses_yaml_into_agent_config(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    config = ConfigLoader.from_yaml(agents_dir, "test_agent")
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
    img = tmp_path / "stop.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    renderer = PromptRenderer("Descrivi.")
    parts = renderer.render({}, images=(img,))
    assert isinstance(parts, list)
    assert any(isinstance(p, BinaryContent) for p in parts)


# --- BaseAgent ---


def test_base_agent_created_from_valid_config(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    config = ConfigLoader.from_yaml(agents_dir, "test_agent")
    agent = BaseAgent(config, str)
    assert agent is not None


def test_base_agent_from_yaml_factory_method(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    agent = BaseAgent.from_yaml("test_agent", agents_dir, str)
    assert agent is not None


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
    agent = BaseAgent.from_yaml("test_agent", agents_dir, str)
    assert agent.core_agent.model_settings["temperature"] == 0.5
    assert agent.core_agent.model_settings["max_tokens"] == 256
    assert agent.core_agent._max_output_retries == 2


def test_base_agent_model_name_slash_converted_to_colon(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    # Should not raise even without OPENROUTER_API_KEY (defer_model_check=True)
    agent = BaseAgent.from_yaml("test_agent", agents_dir, str)
    assert agent is not None
