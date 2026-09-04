"""Agent prompts are loaded through the file-system client, from two resolved anchors.

`AgentConfigRepository.load` reads the API's own, non-epoch agents from
`AppConfig.agents_dir`; `load_judge` reads the epoch-controlled ones from
`LabelingConfig.agents_dir` (D4, ADR 0020). Tests exercising `load` use a non-epoch
agent name (`road_sign_describer`) rather than `comma_labeler`, so they fail if the
two directories ever diverge instead of passing by coincidence.
"""

import pytest
from pywire import get_default_container

from commons.ai.agents import AgentConfig
from guidami_ai_patente.configs import AppConfig
from guidami_ai_patente.repositories import AgentConfigRepository


def test_it_loads_a_prompt_by_bare_name(api_client: object) -> None:
    config = get_default_container().resolve(AgentConfigRepository).load("road_sign_describer")

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
    app_config: AppConfig, api_client: object
) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    assert repository.load("road_sign_describer") == repository.load("road_sign_describer"), (
        "AD-22: `AppConfig.agents_dir` is resolved once, here, for the app's own non-epoch agents"
    )
    assert (app_config.agents_dir / "road_sign_describer.yaml").is_file()


def test_the_app_anchor_loads_a_non_epoch_agent(api_client: object) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    assert repository.load("road_sign_describer").model_name != ""


def test_the_judge_anchor_loads_the_comma_labeler(api_client: object) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    assert repository.load_judge("comma_labeler").model_name != ""


def test_a_name_outside_the_directory_is_refused(api_client: object) -> None:
    repository = get_default_container().resolve(AgentConfigRepository)

    with pytest.raises(PermissionError):
        repository.load("../../.env")
