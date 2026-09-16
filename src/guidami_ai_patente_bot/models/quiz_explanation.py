"""The explanation the bot receives from `GET /quiz-questions/{number}/explanation`."""

from pydantic import BaseModel, ConfigDict

from guidami_ai_patente_bot.enums import ExplanationOutcome


class QuizExplanation(BaseModel):
    """Why the correct answer is correct, or a reasoned refusal (FR-2).

    Deliberately narrower than the API's `QuizExplanationResponse`: the chat message
    shows only the outcome and the prose, never citations, provenance or the judge's
    rationale (FR-2 AC) — those wire fields are simply not modeled here; pydantic
    ignores unknown fields on `model_validate` by default.
    """

    model_config = ConfigDict(frozen=True)

    status: ExplanationOutcome
    explanation: str | None
