from pathlib import Path

from commons.ai.agents import AgentConfig
from domain.enums import LexemeField
from labeling.configs import LabelingConfig
from labeling.mappers import LabelingEpochMapper
from labeling.utils import prompt_version


def _agent_config() -> AgentConfig:
    return AgentConfig(
        model_name="openrouter/google/gemini-2.5-flash-lite",
        system="sistema",
        user="utente",
    )


def _config(**overrides: object) -> LabelingConfig:
    fields: dict[str, object] = {"agents_dir": Path("configs/agents")}
    fields.update(overrides)
    return LabelingConfig(**fields)  # type: ignore[arg-type]


def test_lexeme_fields_are_sorted_regardless_of_the_configured_order() -> None:
    unsorted = _config(
        lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT, LexemeField.IMAGE_DESCRIPTION)
    )

    epoch = LabelingEpochMapper.from_config_to_epoch(unsorted, _agent_config())

    assert epoch.lexeme_fields == ("image_description", "text", "topic")


def test_two_orderings_of_the_same_field_set_give_the_same_epoch() -> None:
    first = _config(lexeme_fields=(LexemeField.TOPIC, LexemeField.TEXT))
    second = _config(lexeme_fields=(LexemeField.TEXT, LexemeField.TOPIC))
    agent_config = _agent_config()

    assert LabelingEpochMapper.from_config_to_epoch(
        first, agent_config
    ) == LabelingEpochMapper.from_config_to_epoch(second, agent_config)


def test_the_prompt_version_is_the_hash_of_the_agent_prompt() -> None:
    agent_config = _agent_config()

    epoch = LabelingEpochMapper.from_config_to_epoch(_config(), agent_config)

    assert epoch.prompt_version == prompt_version(agent_config.system, agent_config.user)


def test_the_judge_model_is_the_agent_model_name() -> None:
    epoch = LabelingEpochMapper.from_config_to_epoch(_config(), _agent_config())

    assert epoch.judge_model == "openrouter/google/gemini-2.5-flash-lite"
