"""Response schemas for the topics endpoint."""

from pydantic import BaseModel


class QuizTopicResponse(BaseModel):
    """One filterable topic and how many questions carry it (FR-16)."""

    topic: str
    question_count: int


class QuizTopicsResponse(BaseModel):
    """Every distinct topic, ordered by name so the menu is stable (FR-16, AD-31)."""

    topics: list[QuizTopicResponse]
