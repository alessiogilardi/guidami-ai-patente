from pydantic import BaseModel, ConfigDict


class ExtractedEntry(BaseModel):
    """One term/definition pair, already attributed to its source comma (FR-3)."""

    model_config = ConfigDict(frozen=True)

    term: str
    definition: str
    comma_number: str
