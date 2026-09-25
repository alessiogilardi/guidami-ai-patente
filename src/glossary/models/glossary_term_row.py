from pydantic import BaseModel, ConfigDict


class GlossaryTermRow(BaseModel):
    """One `glossary_entries` row still needing (or being forced into) a `term_ru` translation."""

    model_config = ConfigDict(frozen=True)

    id: int
    term: str
    definition: str
