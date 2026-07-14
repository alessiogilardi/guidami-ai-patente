"""Tests for the repository-injection signature of BaseAgent.from_yaml.

These tests describe the new contract: callers construct a YamlRepository and
pass it directly to from_yaml instead of passing agents_dir: Path.
"""

from pathlib import Path

import pytest
import yaml
from pydantic_ai.providers.openrouter import OpenRouterProvider

from commons.ai.agents import AgentConfig, BaseAgent
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository

_PROVIDER = OpenRouterProvider(api_key="test-key")

MINIMAL_CONFIG: dict = {
    "model_name": "openrouter/google/gemini-2.5-flash-lite",
    "system": "Sistema di test.",
    "user": "Testo: $input",
}


class _StrAgent(BaseAgent[str, str]):
    output_type = str


def _write_yaml(agents_dir: Path, name: str, content: dict) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.yaml").write_text(yaml.dump(content), encoding="utf-8")


def test_base_agent_from_yaml_accepts_repository(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "test_agent", MINIMAL_CONFIG)
    repository = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))

    agent = _StrAgent.from_yaml("test_agent", repository=repository, provider=_PROVIDER)

    assert agent is not None


def test_base_agent_from_yaml_raises_file_not_found_via_repository(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    repository = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))

    with pytest.raises(FileNotFoundError):
        _StrAgent.from_yaml("nonexistent", repository=repository, provider=_PROVIDER)
