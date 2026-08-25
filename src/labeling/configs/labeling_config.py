from pathlib import Path
from typing import ClassVar

from pydantic import AliasChoices, Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource

from domain.enums import LexemeField


class LabelingConfig(BaseSettings):
    """The judge's identity and its run mechanics, resolved from one file (AD-27).

    Two groups of fields live here, and the difference matters:

    * **Epoch fields** (`EPOCH_FIELDS`) — `agents_dir`, `candidate_variant`, `dense_k`,
      `text_k`, `lexeme_fields`. Together with the `judge_model` and `prompt_version`
      they imply (both derived from the agent YAML found under `agents_dir`), they are
      what `labeling_runs`' partial unique index keys on. Changing any of them opens a
      **new** configuration epoch, which invalidates every cached labeling without a
      single `DELETE`.
    * **Run mechanics** — `shuffle_seed`, `concurrency`, `transport_retries`,
      `retry_backoff_seconds`. They live here for cohesion but never enter the epoch
      key. `shuffle_seed` is recorded on the run as provenance; the other three are
      not recorded at all.

    Resolved from `configs/labeling.yaml` plus the environment, and embedded in both
    `IngestorConfig` and `AppConfig`, so the batch judge and the live judge cannot
    disagree about their own identity (AD-22, AD-27).
    """

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_file=".env",
        yaml_file="configs/labeling.yaml",
    )

    EPOCH_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"agents_dir", "candidate_variant", "dense_k", "text_k", "lexeme_fields"}
    )

    agents_dir: Path = Field(
        validation_alias=AliasChoices("AGENTS_DIR", "agents_dir"),
        description=(
            "Directory holding the agent YAML files. Deliberately defaultless: "
            "prompt_version is a hash of the prompt text, so two deployments "
            "resolving different files would silently produce a permanent 100% "
            "cache miss (AD-22)."
        ),
    )
    candidate_variant: str = "topic_text"
    dense_k: int = 50
    text_k: int = 50
    lexeme_fields: tuple[LexemeField, ...] = (
        LexemeField.TOPIC,
        LexemeField.TEXT,
        LexemeField.IMAGE_DESCRIPTION,
    )
    shuffle_seed: int = 42
    concurrency: int = 8
    transport_retries: int = 3
    retry_backoff_seconds: float = 2.0

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Precedence: init > env/.env > `configs/labeling.yaml`."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    @field_validator("dense_k", "text_k")
    @classmethod
    def _validate_depths(cls, value: int, info: ValidationInfo) -> int:
        """Rejects an arm depth below 1: FR-5 has no candidates to union otherwise."""
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1, got {value}")
        return value

    @field_validator("concurrency")
    @classmethod
    def _validate_concurrency(cls, value: int) -> int:
        """Rejects a concurrency below 1: FR-10 needs at least one in-flight call."""
        if value < 1:
            raise ValueError(f"concurrency must be >= 1, got {value}")
        return value

    @field_validator("transport_retries")
    @classmethod
    def _validate_transport_retries(cls, value: int) -> int:
        """Rejects a value below 1: 1 means "attempt once, do not retry"; 0 has no meaning."""
        if value < 1:
            raise ValueError(f"transport_retries must be >= 1, got {value}")
        return value

    @field_validator("retry_backoff_seconds")
    @classmethod
    def _validate_retry_backoff(cls, value: float) -> float:
        """Rejects a non-positive backoff: a zero/negative sleep is not a real backoff."""
        if value <= 0:
            raise ValueError(f"retry_backoff_seconds must be > 0, got {value}")
        return value

    @field_validator("lexeme_fields")
    @classmethod
    def _validate_lexeme_fields(cls, value: tuple[LexemeField, ...]) -> tuple[LexemeField, ...]:
        """Rejects an empty selection and a repeated field (FR-4).

        A field named twice would concatenate its text twice and silently double its
        weight in the extracted lexemes.
        """
        if not value:
            raise ValueError("lexeme_fields must name at least one field")
        duplicates = sorted({field.value for field in value if value.count(field) > 1})
        if duplicates:
            raise ValueError(f"lexeme_fields must not repeat a field, got {duplicates}")
        return value
