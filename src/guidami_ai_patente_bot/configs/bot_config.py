"""Root configuration for the Telegram bot process (ADR 0032)."""

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from commons.configs import BaseConfig


class BotConfig(BaseConfig):
    """Settings for the Telegram bot process.

    Built once at the entry point (`main.py`) and registered on the pywire container
    as a single instance — never loaded inside handlers or services, the same
    posture `AppConfig` and `ObservabilityConfig` already use. `telegram_bot_token`
    has no default: a missing token is a loud `ValidationError` at startup, mirroring
    `OpenRouterConfig.api_key` and `AppConfig.agents_dir`.
    """

    model_config = SettingsConfigDict(yaml_file="configs/bot_config.yaml")

    telegram_bot_token: SecretStr
    api_base_url: str = "http://localhost:8000"
    request_timeout_seconds: float = Field(default=15.0, gt=0.0)
    telegram_read_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description=(
            "Read timeout for python-telegram-bot's own HTTPXRequest, i.e. how long "
            "to wait for Telegram's API response (e.g. after a send_photo upload). "
            "Distinct from request_timeout_seconds, which times out QuizApiClient's "
            "calls to our own backend, not calls to api.telegram.org. "
            "python-telegram-bot's default (5.0s) is too short for send_photo: "
            "Telegram can take longer than that to process an uploaded image and "
            "reply, which previously surfaced as an unhandled telegram.error.TimedOut."
        ),
    )
