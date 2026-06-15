from pathlib import Path

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource

from commons.configs import EmbeddingConfig, VectorStoreConfig


class IngestorConfig(BaseSettings):
    """Configurazione della pipeline di indicizzazione (CdS + CAP)."""

    model_config = SettingsConfigDict(
        frozen=True,
        env_nested_delimiter="__",
        env_file=".env",
        yaml_file="configs/ingestor_config.yaml",
    )

    cds_parsed_path: Path = Path("data/parsed/cds/codice_della_strada.json")
    cds_cleaned_path: Path = Path("data/cleaned/cds/codice_della_strada.json")
    cap_parsed_path: Path = Path("data/parsed/cap/codice_rca.json")
    cap_cleaned_path: Path = Path("data/cleaned/cap/codice_rca.json")
    embedding_batch_size: int = 64
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig

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
