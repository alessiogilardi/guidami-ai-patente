"""Mirrors the API's explanation_status vocabulary, declared locally for HTTP coupling."""

from enum import StrEnum, auto


class ExplanationStatus(StrEnum):
    """The `explanation_status` field of `POST /quiz-questions/{number}/check` (spec 0017, FR-6).

    Declared locally rather than imported from `guidami_ai_patente.enums.ExplanationStatus`:
    the bot is coupled to the API only through its HTTP wire contract (AD-1), never a
    Python import of the API package's own types — same reasoning as `ExplanationOutcome`.
    """

    CACHED = auto()
    UNCACHED = auto()
    UNAVAILABLE = auto()
