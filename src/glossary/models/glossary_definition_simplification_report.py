from pydantic import BaseModel, ConfigDict


class GlossaryDefinitionSimplificationReport(BaseModel):
    """The full result of one `simplify-glossary-definitions` run."""

    model_config = ConfigDict(frozen=True)

    simplified: int
    still_missing: int
