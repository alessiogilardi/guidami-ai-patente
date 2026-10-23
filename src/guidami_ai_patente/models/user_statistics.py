"""A user's overall mastery statistics."""

from pydantic import BaseModel, ConfigDict

from .topic_mastery import TopicMastery


class UserStatistics(BaseModel):
    """Aggregate answer, coverage and mastery counts, with the per-topic breakdown."""

    model_config = ConfigDict(frozen=True)

    answered: int
    seen: int
    bank_total: int
    mastered: int
    in_review: int
    topics: list[TopicMastery]
