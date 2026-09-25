from pydantic import BaseModel, ConfigDict, Field


class GlossaryEmbeddingConfig(BaseModel):
    """Embedding settings for glossary term/definition pairs (FR-6)."""

    model_config = ConfigDict(frozen=True)

    batch_size: int = Field(default=16, ge=1)
