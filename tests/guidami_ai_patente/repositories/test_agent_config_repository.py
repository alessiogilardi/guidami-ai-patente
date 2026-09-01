"""Agent prompts are loaded through the file-system client, from one resolved dir."""

import pytest
from pywire import get_default_container

from commons.ai.agents import AgentConfig
from guidami_ai_patente.repositories import AgentConfigRepository
from labeling.configs import LabelingConfig


def test_it_loads_a_prompt_by_bare_name(api_client: object) -> None:
    config = get_default_container().resolve(AgentConfigRepository).load("comma_labeler")

    assert isinstance(config, AgentConfig)
    assert config.system and config.user


def test_an_unknown_agent_raises_file_not_found(api_client: object) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    with pytest.raises(FileNotFoundError):
        repository.load("no_such_agent")


def test_a_traversal_name_is_refused_by_the_client(api_client: object) -> None:
    """The FS client anchors every read to `agents_dir`; nothing above it is reachable."""
    repository = get_default_container().resolve(AgentConfigRepository)

    with pytest.raises((PermissionError, FileNotFoundError)):
        repository.load("../../.env")


def test_it_reads_from_the_configured_agents_dir(
    labeling_config: LabelingConfig, api_client: object
) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    assert repository.load("comma_labeler") == repository.load("comma_labeler"), (
        "AD-22: `agents_dir` is resolved once, here, and nowhere else in the API"
    )
    assert (labeling_config.agents_dir / "comma_labeler.yaml").is_file()
