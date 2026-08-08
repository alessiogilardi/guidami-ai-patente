"""Root configuration for the FastAPI service."""

from pydantic_settings import BaseSettings, SettingsConfigDict

from commons.configs import PostgresConnectionConfig


class AppConfig(BaseSettings):
    """Root settings for the guidami-ai-patente API service.

    Built once at the entry point (`main.py`) and passed down to the app
    factory and its dependencies — never loaded inside routers or services.
    """

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    postgres: PostgresConnectionConfig
