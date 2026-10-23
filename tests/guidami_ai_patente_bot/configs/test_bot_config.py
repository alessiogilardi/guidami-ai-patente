"""BotConfig loads Telegram bot settings; the token is a required secret (ADR 0032)."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente_bot.configs import BotConfig


def test_the_api_base_url_and_timeout_have_defaults() -> None:
    assert BotConfig.model_fields["api_base_url"].default == "http://localhost:8000"
    assert BotConfig.model_fields["request_timeout_seconds"].default == 15.0


def test_the_topic_label_max_chars_defaults_to_40() -> None:
    assert BotConfig.model_fields["topic_label_max_chars"].default == 40


def test_a_topic_label_max_chars_below_ten_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")

    with pytest.raises(ValidationError):
        BotConfig(_env_file=None, topic_label_max_chars=9)  # pyright: ignore[reportCallIssue]


def test_the_telegram_bot_token_has_no_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        BotConfig(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_the_telegram_bot_token_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")

    config = BotConfig(_env_file=None)  # pyright: ignore[reportCallIssue]

    assert config.telegram_bot_token.get_secret_value() == "secret-token"
