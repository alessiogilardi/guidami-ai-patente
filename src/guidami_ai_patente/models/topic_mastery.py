"""One topic's slice of a user's statistics."""

from pydantic import BaseModel, ConfigDict


class TopicMastery(BaseModel):
    """Seen and mastered question counts for a topic, against the topic's total."""

    model_config = ConfigDict(frozen=True)

    topic: str
    seen: int
    mastered: int
    total: int
    insufficient_data: bool
