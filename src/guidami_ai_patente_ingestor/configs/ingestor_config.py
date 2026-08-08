from pathlib import Path
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource

from commons.ai.embedding import EmbeddingClientConfig
from commons.configs import OpenRouterConfig, PostgresConnectionConfig

from .evaluation_config import EvaluationConfig
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
            "reg": SourceConfig(dir="reg", file="regolamento_attuazione.json"),
            "amb": SourceConfig(dir="amb", file="codice_ambiente_rifiuti.json"),
            "quiz": SourceConfig(dir="quiz-patente-ab", file="quiz-patente-ab.json"),
        }
    )
    knowledge_preparation: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="parsed", output_layer="cleaned", sources=["cds", "cap", "reg", "amb"]
    )
    knowledge_indexing: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="cleaned", sources=["cds", "cap", "reg", "amb"]
    )
    quiz_preparation: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="parsed", output_layer="enriched", sources=["quiz"]
    )
    quiz_indexing: PipelineLayerConfig = PipelineLayerConfig(
        input_layer="enriched", sources=["quiz"]
    )
    agents_dir: Path = Path("configs/agents")
    quiz_images_dir: Path = Path("data/quiz-images")
    project_root: Path = Path(".")

    embedding_batch_size: int = 64
    road_sign_describer_concurrency: int = 8
    norm_reference_describer_concurrency: int = 8
    embedding: EmbeddingClientConfig = EmbeddingClientConfig()
    postgres: PostgresConnectionConfig
    articles_table: str = "articles"
    article_commas_table: str = "article_commas"
    quiz_questions_table: str = "quiz_questions"
    quiz_question_embeddings_table: str = "quiz_question_embeddings"
    quiz_images_table: str = "quiz_images"
    embed_repealed: bool = False
    quiz_embedding_variants: list[str] = Field(
        default_factory=lambda: [
            "text",
            "topic_text",
            "search_queries",
            "combined",
            "combined_description",
            "image_description",
        ]
    )
    rca_ranges: list[str] = Field(default_factory=lambda: ["118-165", "278-300"])
    amb_ranges: list[str] = Field(default_factory=lambda: ["227-237"])
    evaluation: EvaluationConfig = EvaluationConfig()

    _config_override_file: ClassVar[Path | None] = None
    """Set (on a dynamically-created subclass, never on `IngestorConfig` itself) by
    `load()` to point `settings_customise_sources` at an extra, higher-precedence
    yaml source layered on top of the default `configs/ingestor_config.yaml`.
    """

    @classmethod
    def load(cls, config_override: Path | None = None, **init_kwargs: object) -> "IngestorConfig":
        """Builds the config, optionally layering `config_override` over the base yaml.

        `config_override` (e.g. `configs/ingestor_config.test-data.yaml`) only needs to
        set the fields that actually differ from the base yaml — it becomes its own
        `YamlConfigSettingsSource`, positioned between env/.env and the base yaml, so
        fields it doesn't mention still fall through to the base yaml (see ADR 0006).
        `init_kwargs` are forwarded to the constructor unchanged (highest precedence).

        Note: with `config_override` set, the returned instance is of a dynamically
        created `IngestorConfig` subclass (carrying `config_override` as its
        `_config_override_file`), not of `IngestorConfig` itself — hence the plain
        `IngestorConfig` return type rather than `Self`.
        """
        if config_override is None:
            return cls(**init_kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]
        subclass = type(cls.__name__, (cls,), {"_config_override_file": config_override})
        return subclass(**init_kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Precedence: init > env/.env (secrets) > override yaml (`load()`) > base yaml."""
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        override_file = getattr(settings_cls, "_config_override_file", None)
        if override_file is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=override_file))
        sources.append(YamlConfigSettingsSource(settings_cls))
        return tuple(sources)
