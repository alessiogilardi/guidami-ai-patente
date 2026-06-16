from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource

from commons.configs import EmbeddingConfig, PostgresConnectionConfig


class IngestorConfig(BaseSettings):
    """Configurazione delle pipeline di ingestion (corpus normativo CdS + CAP, quiz bank)."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
        yaml_file="configs/ingestor_config.yaml",
    )

    cds_parsed_path: Path = Path("data/parsed/cds/codice_della_strada.json")
    cds_cleaned_path: Path = Path("data/cleaned/cds/codice_della_strada.json")
    cap_parsed_path: Path = Path("data/parsed/cap/codice_rca.json")
    cap_cleaned_path: Path = Path("data/cleaned/cap/codice_rca.json")
    quiz_bank_path: Path = Path("data/cleaned/quiz-patente-ab/quiz-patente-ab.json")
    openrouter_api_key: SecretStr | None = None
    embedding_batch_size: int = 64
    embedding: EmbeddingConfig = EmbeddingConfig()
    postgres: PostgresConnectionConfig
    knowledge_chunks_table: str = "knowledge_chunks"
    quiz_questions_table: str = "quiz_questions"
    embed_repealed: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Precedenza: init > env/.env (secrets) > ingestor_config.yaml (non-secrets)."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )
