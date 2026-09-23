"""Per-chat state kept in `context.user_data` for the process lifetime (AD-2)."""

from pydantic import BaseModel, ConfigDict

from guidami_ai_patente_bot.models.cited_glossary_term import CitedGlossaryTerm


class QuizSession(BaseModel):
    """The seeded permutation position and the question currently on screen.

    `current_question_number` is what a stale button tap is compared against (FR-3).
    `last_explanation` holds the Italian text last shown by "Spiega" for that same
    question (spec 0018 bot UX) — `None` until an explanation has actually been
    displayed. A "Traduci" tap treats a `None` value as its own staleness signal,
    exactly like a `current_question_number` mismatch.
    `last_explanation_hints` carries glossary terms in Italian and Russian for
    on-demand translation to a user's preferred language (spec 0020).
    """

    model_config = ConfigDict(frozen=True)

    seed: str
    index: int
    current_question_number: str
    last_explanation: str | None = None
    last_explanation_hints: tuple[CitedGlossaryTerm, ...] = ()
