from pydantic import BaseModel, ConfigDict


class GlossaryTermTranslationReport(BaseModel):
    """The full result of one `translate-glossary-terms` run."""

    model_config = ConfigDict(frozen=True)

    translated: int
    still_missing: int
