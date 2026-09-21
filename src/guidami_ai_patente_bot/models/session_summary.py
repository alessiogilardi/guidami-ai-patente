"""The session summary the bot receives from `GET /quiz-answers/summary` (spec 0016, FR-9)."""

from pydantic import BaseModel, ConfigDict

from .topic_summary import TopicSummary
from .wrong_question import WrongQuestion


class SessionSummary(BaseModel):
    """A session's totals, its per-topic breakdown and the questions worth reviewing.

    Field-for-field mirror of the backend's own `SessionSummaryResponse`: declared
    independently, same posture as `QuizQuestion`/`QuizExplanation` (AD-1).
    """

    model_config = ConfigDict(frozen=True)

    answered: int
    correct: int
    by_topic: list[TopicSummary]
    wrong_questions: list[WrongQuestion]
