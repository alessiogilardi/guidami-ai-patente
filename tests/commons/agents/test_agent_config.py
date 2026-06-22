import pytest
from pydantic import ValidationError

from commons.configs import AgentConfig


def test_agent_config_parses_from_dict() -> None:
    data = {
        "model_name": "openrouter/google/gemini-2.5-flash-lite",
        "system": "Sei un esperto.",
        "user": "Descrivi: $input",
    }
    config = AgentConfig.model_validate(data)
    assert config.model_name == "openrouter/google/gemini-2.5-flash-lite"
    assert config.system == "Sei un esperto."
    assert config.user == "Descrivi: $input"


def test_agent_config_applies_defaults() -> None:
    config = AgentConfig.model_validate(
        {
            "model_name": "openrouter/google/gemini-2.5-flash-lite",
            "system": "System.",
            "user": "User.",
        }
    )
    assert config.temperature == 0.0
    assert config.max_tokens is None
    assert config.timeout == 60.0
    assert config.num_retries == 3


def test_agent_config_missing_model_name_raises() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"system": "Sys.", "user": "User."})


def test_agent_config_missing_system_raises() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate(
            {"model_name": "openrouter/google/gemini-2.5-flash-lite", "user": "User."}
        )


def test_agent_config_is_frozen() -> None:
    config = AgentConfig.model_validate(
        {
            "model_name": "openrouter/google/gemini-2.5-flash-lite",
            "system": "Sys.",
            "user": "User.",
        }
    )
    with pytest.raises(ValidationError):
        config.model_name = "other"  # type: ignore[misc]
