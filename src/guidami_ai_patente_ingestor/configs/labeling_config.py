from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

from domain.enums import LexemeField


class LabelingConfig(BaseModel):
    """Run parameters for the golden-set labeling pass (spec 0011, FR-4/FR-5/FR-11).

    Every field has a default so the labeler runs with no configuration override;
    `label-golden-set --concurrency`/`--seed` layer a CLI override on top of these,
    and `--limit` restricts the run to a subset with no corresponding config field
    (it names how many questions, not a run parameter that persists across runs).
    """

    model_config = ConfigDict(frozen=True)

    candidate_variant: str = "topic_text"
    dense_k: int = 50
    text_k: int = 50
    shuffle_seed: int = 42
    concurrency: int = 8
    transport_retries: int = 3
    retry_backoff_seconds: float = 2.0
    lexeme_fields: tuple[LexemeField, ...] = (
        LexemeField.TOPIC,
        LexemeField.TEXT,
        LexemeField.IMAGE_DESCRIPTION,
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
