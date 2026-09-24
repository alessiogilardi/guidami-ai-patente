from pydantic import BaseModel, Field


class GlossaryExtractorRequest(BaseModel):
    """One chunk of one block's text, ready for extraction (FR-3)."""

    block_text: str = Field(min_length=1)
