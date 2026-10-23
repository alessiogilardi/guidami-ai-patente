"""Response schema for GET /quiz-answers/summary."""

from pydantic import BaseModel


class TopicSummaryResponse(BaseModel):
    """How many answers a session recorded for one topic, and how many were correct."""

    topic: str
    answered: int
    correct: int


class WrongQuestionResponse(BaseModel):
    """A question answered wrongly at least once in the session: its number and text."""

    number: str
    text: str


class TopicMasteryResponse(BaseModel):
    """One topic's seen/mastered counts against its total, for GET /statistics."""

    topic: str
    seen: int
    mastered: int
    total: int
    insufficient_data: bool


class UserStatisticsResponse(BaseModel):
    """A user's answer, coverage and mastery counts with the ranked topic breakdown."""

    answered: int
    seen: int
    bank_total: int
    mastered: int
    in_review: int
    topics: list[TopicMasteryResponse]


class SessionSummaryResponse(BaseModel):
    """A session's totals, its per-topic breakdown and the questions worth reviewing."""

    answered: int
    correct: int
    by_topic: list[TopicSummaryResponse]
    wrong_questions: list[WrongQuestionResponse]
