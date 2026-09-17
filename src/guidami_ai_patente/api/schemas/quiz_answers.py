"""Response schema for GET /quiz-answers/summary."""

from pydantic import BaseModel


class SessionSummaryResponse(BaseModel):
    """How many questions were answered in the session, and how many were correct."""

    answered: int
    correct: int
