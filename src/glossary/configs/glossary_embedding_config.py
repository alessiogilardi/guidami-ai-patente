from pydantic import BaseModel, ConfigDict, field_validator


class GlossaryEmbeddingConfig(BaseModel):
    """Embedding settings for glossary term/definition pairs (FR-6)."""

    model_config = ConfigDict(frozen=True)

    batch_size: int = 16

    @field_validator("batch_size")
    @classmethod
    def _validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"batch_size must be >= 1, got {value}")
        return value
