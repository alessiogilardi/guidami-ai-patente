"""The explanation the bot receives from `GET /quiz-questions/{number}/explanation`."""

from pydantic import BaseModel, ConfigDict

from guidami_ai_patente_bot.enums import ExplanationOutcome
from guidami_ai_patente_bot.models.cited_glossary_term import CitedGlossaryTerm


class QuizExplanation(BaseModel):
    """Why the correct answer is correct, or a reasoned refusal (FR-2).

    Deliberately narrower than the API's `QuizExplanationResponse`: the chat message
    shows only the outcome and the prose, never citations, provenance or the judge's
    rationale (FR-2 AC) — those wire fields are simply not modeled here; pydantic
    ignores unknown fields on `model_validate` by default.

    `term_explanation` is an optional additional explanation focused on the terminology
    of the question (spec 0020). `translation_hints` carries glossary terms in Italian
    and Russian for on-demand translation to a user's preferred language.
    """

    model_config = ConfigDict(frozen=True)

    status: ExplanationOutcome
    explanation: str | None
    term_explanation: str | None = None
    translation_hints: tuple[CitedGlossaryTerm, ...] = ()
