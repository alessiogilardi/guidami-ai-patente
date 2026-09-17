"""The session summary the bot receives from `GET /quiz-answers/summary` (spec 0016, FR-9)."""

from pydantic import BaseModel, ConfigDict


class SessionSummary(BaseModel):
    """How many questions were answered in the session, and how many were correct.

    Field-for-field mirror of the backend's own `SessionSummaryResponse`: declared
    independently, same posture as `QuizQuestion`/`QuizExplanation` (AD-1).
    """

    model_config = ConfigDict(frozen=True)

    answered: int
    correct: int
