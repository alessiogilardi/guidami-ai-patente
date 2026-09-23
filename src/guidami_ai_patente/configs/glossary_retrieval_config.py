"""Deployment configuration for the vocabulary explanation stage's glossary retrieval."""

from pydantic import BaseModel, ConfigDict, Field


class GlossaryRetrievalConfig(BaseModel):
    """Retrieval depths and table name for `GlossaryReadRepository` (FR-4, spec 0020).

    Deployment configuration, never judge identity — same status as
    `AppConfig.explanation_deadline_s`. Nested under `AppConfig.glossary`, mirroring
    `AppConfig.postgres: PostgresConnectionConfig`'s existing shape in this package.
    """

    model_config = ConfigDict(frozen=True)

    entries_table: str = "glossary_entries"
    dense_k: int = Field(
        default=5, gt=0, description="Dense arm depth for glossary retrieval (FR-4)."
    )
    text_k: int = Field(
        default=5, gt=0, description="Full-text arm depth for glossary retrieval (FR-4)."
    )
    max_candidates: int = Field(
        default=10,
        gt=0,
        description=(
            "Cap on the deduplicated candidate union handed to QuestionExplainerAgent (FR-4)."
        ),
    )
