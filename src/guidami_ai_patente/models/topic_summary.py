"""One topic's slice of a session summary."""

from pydantic import BaseModel, ConfigDict


class TopicSummary(BaseModel):
    """How many answers a session recorded for one topic, and how many were correct."""

    model_config = ConfigDict(frozen=True)

    topic: str
    answered: int
    correct: int
