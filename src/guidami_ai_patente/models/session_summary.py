"""A session's answered/correct counts (spec 0016, FR-9, AD-16)."""

from pydantic import BaseModel, ConfigDict


class SessionSummary(BaseModel):
    """How many questions were answered in a session, and how many were correct."""

    model_config = ConfigDict(frozen=True)

    answered: int
    correct: int
