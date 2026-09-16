"""Outcome of an explanation request, mirroring guidami_ai_patente's wire vocabulary."""

from enum import StrEnum, auto


class ExplanationOutcome(StrEnum):
    """The `status` field of `GET /quiz-questions/{number}/explanation` (FR-2).

    Declared locally rather than imported from `guidami_ai_patente.enums.ExplanationResult`:
    the bot is coupled to the API only through its HTTP wire contract (AD-1), never a
    Python import of the API package's own types. Values are chosen to match the wire
    strings exactly, so `QuizExplanation.model_validate` needs no alias.
    """

    EXPLAINED = auto()
    INSUFFICIENT_KNOWLEDGE = auto()
