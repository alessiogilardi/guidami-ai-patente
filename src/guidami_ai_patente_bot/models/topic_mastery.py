"""One topic's mastery counts as received from `GET /quiz-answers/statistics`."""

from pydantic import BaseModel, ConfigDict


class TopicMastery(BaseModel):
    """One topic's seen/mastered counts against its total.

    Field-for-field mirror of the backend's `TopicMasteryResponse` wire shape: declared
    independently, same posture as `TopicSummary` (spec 0015 AD-1).
    """

    model_config = ConfigDict(frozen=True)

    topic: str
    seen: int
    mastered: int
    total: int
    insufficient_data: bool
