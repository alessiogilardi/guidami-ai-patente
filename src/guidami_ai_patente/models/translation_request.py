"""The translation UseCase's input: the Italian text, and any term hints to honor."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .translation_hint import TranslationHint


class TranslationRequest(BaseModel):
    """Two arguments, so a request DTO rather than a bare `str`
    (`.claude/rules/use-case-invocation.md`).

    Not the same type as
    `api/schemas/explanation_translation.py::ExplanationTranslationRequest`: that one
    is the wire-format request body. This one is
    `ExplanationTranslationService`'s `UseCase` input, assembled by the router from
    the body.

    Attributes:
        text: The Italian text to translate to Russian.
        hints: Already-reviewed term translations the agent should honor (FR-8).
            Empty by default: a request with no hints behaves exactly as before this
            amendment. No two hints may share the same `term` (case-insensitive):
            contradictory renderings for the same word would just confuse the agent.
    """

    model_config = ConfigDict(frozen=True)

    text: str = Field(min_length=1)
    hints: tuple[TranslationHint, ...] = ()

    @model_validator(mode="after")
    def _reject_duplicate_hint_terms(self) -> "TranslationRequest":
        """Mirrors `ExplanationWriterResponse._reject_repeated_ordinals`'s pattern."""
        terms = [hint.term.lower() for hint in self.hints]
        if len(set(terms)) != len(terms):
            raise ValueError("hints must not repeat the same term")
        return self
