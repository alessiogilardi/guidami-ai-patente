"""One topic's slice of the session summary the bot receives (spec 0016, FR-9)."""

from pydantic import BaseModel, ConfigDict


class TopicSummary(BaseModel):
    """How many answers a session recorded for one topic, and how many were correct.

    Field-for-field mirror of the backend's own `TopicSummaryResponse`: declared
    independently, same posture as `SessionSummary` (AD-1).
    """

    model_config = ConfigDict(frozen=True)

    topic: str
    answered: int
    correct: int
