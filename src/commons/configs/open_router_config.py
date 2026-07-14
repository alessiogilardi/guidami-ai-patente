from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenRouterConfig(BaseSettings):
    """OpenRouter credentials, read from `OPENROUTER_*` environment variables."""

    model_config = SettingsConfigDict(
        frozen=True,
        env_prefix="OPENROUTER_",
        env_file=".env",
        extra="ignore",
    )

    api_key: SecretStr
