"""A term-translation pairing a caller already trusts (spec 0018, FR-8)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TranslationHint(BaseModel):
    """Anchors one Italian term to its already-reviewed Russian rendering.

    Shared across the translation request boundary and the translator agent's own
    request DTO — mirrors `LabeledComma`'s reuse across the explanation pipeline.

    Advisory, not a verbatim substitution (AD-9): the agent still inflects `term_ru`
    into the sentence's grammatical case (case, number) as a human translator would
    use a dictionary entry, rather than splicing it in unchanged.
    """

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1, max_length=80)
    term_ru: str = Field(min_length=1, max_length=80)

    @field_validator("term", "term_ru")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """`min_length=1` alone accepts a whitespace-only string (grilling round, 2026-09-23)."""
        if not value.strip():
            raise ValueError("must not be blank")
        return value
