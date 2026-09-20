"""Request and response schemas for the explanation translation endpoint (spec 0018)."""

from pydantic import BaseModel, Field


class ExplanationTranslationRequest(BaseModel):
    """The Italian text to translate — already obtained by the client (FR-1)."""

    text: str = Field(min_length=1, max_length=6000)


class ExplanationTranslationResponse(BaseModel):
    """The Russian translation of the submitted text."""

    translated_text: str
