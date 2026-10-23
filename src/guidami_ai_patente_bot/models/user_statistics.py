"""The user statistics the bot receives from `GET /quiz-answers/statistics`."""

from pydantic import BaseModel, ConfigDict

from .topic_mastery import TopicMastery


class UserStatistics(BaseModel):
    """A user's answer, coverage and mastery counts with the ranked topic breakdown.

    Field-for-field mirror of the backend's `UserStatisticsResponse` wire shape: declared
    independently, same posture as `SessionSummary` (spec 0015 AD-1).
    """

    model_config = ConfigDict(frozen=True)

    answered: int
    seen: int
    bank_total: int
    mastered: int
    in_review: int
    topics: list[TopicMastery]
