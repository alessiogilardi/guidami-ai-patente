"""Input of the explanation translator: the Italian text to render in Russian."""

from pydantic import BaseModel, Field


class ExplanationTranslatorRequest(BaseModel):
    """The Italian text to translate, and nothing else (spec 0018, FR-1).

    Request DTOs stay documented in English: the value is substituted into the
    user-prompt template, but this docstring is never shipped to the model as
    schema — only `ExplanationTranslatorResponse`'s is.

    Attributes:
        text: The Italian text to translate to Russian.
    """

    text: str = Field(min_length=1)
