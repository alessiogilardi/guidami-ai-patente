from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource

from commons.ai.embedding import EmbeddingConfig
from commons.configs import OpenRouterConfig, PostgresConnectionConfig

from .pipeline_layer_config import PipelineLayerConfig
from .source_config import SourceConfig


class IngestorConfig(BaseSettings):
    """Configuration for the ingestion pipelines (corpus normativo CdS + CAP, quiz bank)."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_nested_delimiter="__",
        env_file=".env",
        yaml_file="configs/ingestor_config.yaml",
    )

    open_router_config: OpenRouterConfig = Field(
        default_factory=OpenRouterConfig  # pyright: ignore[reportArgumentType]
    )
    layers: dict[str, str] = Field(
        default_factory=lambda: {
            "parsed": "data/parsed",
            "cleaned": "data/cleaned",
            "enriched": "data/enriched",
        }
    )
    sources: dict[str, SourceConfig] = Field(
        default_factory=lambda: {
            "cds": SourceConfig(dir="cds", file="codice_della_strada.json"),
            "cap": SourceConfig(dir="cap", file="codice_rca.json"),
            "quiz": SourceConfig(dir="quiz-patente-ab", file="quiz-patente-ab.json"),
        }
    )
    knowledge_preparation: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="parsed", output_layer="enriched", sources=["cds", "cap"]
    )
    knowledge_indexing: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="enriched", sources=["cds", "cap"]
    )
    quiz_preparation: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="parsed", output_layer="enriched", sources=["quiz"]
    )
    quiz_indexing: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="enriched", sources=["quiz"]
    )
    agents_dir: Path = Path("configs/agents")
    quiz_images_dir: Path = Path("data/parsed/quiz-patente-ab/images")
    project_root: Path = Path(".")

    embedding_batch_size: int = 64
    road_sign_describer_concurrency: int = 8
    norm_reference_describer_concurrency: int = 8
    article_contextualizer_concurrency: int = 8
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
        """Precedence: init > env/.env (secrets) > ingestor_config.yaml (non-secrets)."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )
