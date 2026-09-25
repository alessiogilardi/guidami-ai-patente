from pydantic import BaseModel, ConfigDict


class GlossaryDefinitionRow(BaseModel):
    """One `glossary_entries` row still needing (or being forced into) a `definition_plain`."""

    model_config = ConfigDict(frozen=True)

    id: int
    term: str
    definition: str
