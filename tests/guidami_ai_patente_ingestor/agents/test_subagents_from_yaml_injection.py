"""Tests for the repository-injection signature of agent subclass from_yaml methods.

Each agent subclass accepts a YamlRepository instead of agents_dir: Path via the
inherited BaseAgent.from_yaml, with no override and no `# type: ignore` suppression.
"""

from pathlib import Path

import yaml

from commons.ai.agents import AgentConfig
from commons.clients.file_system import LocalFileSystemClient
from commons.repositories import YamlRepository
from guidami_ai_patente_ingestor.agents import (
    ArticleContextualizerAgent,
    NormReferenceDescriberAgent,
    RoadSignDescriberAgent,
)

MINIMAL_CONFIG: dict = {
    "model_name": "openrouter/google/gemini-2.5-flash-lite",
    "system": "Sistema di test.",
    "user": "Testo: $input",
}


def _write_yaml(agents_dir: Path, name: str, content: dict) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.yaml").write_text(yaml.dump(content), encoding="utf-8")


def test_article_contextualizer_from_yaml_accepts_repository(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "article_contextualizer", MINIMAL_CONFIG)
    repository = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))

    agent = ArticleContextualizerAgent.from_yaml("article_contextualizer", repository=repository)

    assert agent is not None
    assert isinstance(agent, ArticleContextualizerAgent)


def test_road_sign_describer_from_yaml_accepts_repository(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "road_sign_describer", MINIMAL_CONFIG)
    repository = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))

    agent = RoadSignDescriberAgent.from_yaml(
        "road_sign_describer",
        repository=repository,
        file_reader=LocalFileSystemClient(agents_dir),
    )

    assert agent is not None
    assert isinstance(agent, RoadSignDescriberAgent)


def test_norm_reference_describer_from_yaml_accepts_repository(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    _write_yaml(agents_dir, "norm_reference_describer", MINIMAL_CONFIG)
    repository = YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))

    agent = NormReferenceDescriberAgent.from_yaml(
        "norm_reference_describer", repository=repository
    )

    assert agent is not None
    assert isinstance(agent, NormReferenceDescriberAgent)
