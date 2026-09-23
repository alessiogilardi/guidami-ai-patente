"""Request and response schemas for the explanation translation endpoint (spec 0018)."""

from pydantic import BaseModel, Field, field_validator, model_validator


class TranslationHintRequest(BaseModel):
    """One term the client already has a reviewed Russian rendering for (FR-8).

    Not the same type as `guidami_ai_patente.models.TranslationHint`: that one is the
    translation UseCase's own input shape. This one is the wire-format field inside
    `ExplanationTranslationRequest`.
    """

    term: str = Field(min_length=1, max_length=80)
    term_ru: str = Field(min_length=1, max_length=80)

    @field_validator("term", "term_ru")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """Same rule as `TranslationHint._reject_blank` (grilling round, 2026-09-23)."""
        if any(ord(char) < 0x20 for char in value):
            raise ValueError("must not contain control characters")
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class ExplanationTranslationRequest(BaseModel):
    """The Italian text to translate — already obtained by the client (FR-1).

    `hints` optionally anchors specific terms to an already-reviewed Russian
    rendering (FR-8). Empty by default: a request with no `hints` behaves exactly as
    before this field existed. No two hints may share the same `term`
    (case-insensitive).
    """

    text: str = Field(min_length=1, max_length=6000)
    hints: list[TranslationHintRequest] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _reject_duplicate_hint_terms(self) -> "ExplanationTranslationRequest":
        """Same rule as `TranslationRequest._reject_duplicate_hint_terms`.

        A contradictory pair of hints is a `422` here rather than a `500` from
        `TranslationRequest`'s own validator inside the router (grilling round,
        2026-09-23).
        """
        terms = [hint.term.lower() for hint in self.hints]
        if len(set(terms)) != len(terms):
            raise ValueError("hints must not repeat the same term")
        return self


class ExplanationTranslationResponse(BaseModel):
    """The Russian translation of the submitted text."""

    translated_text: str
