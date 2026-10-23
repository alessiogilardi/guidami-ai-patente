"""Maps the internal user statistics onto the wire contract."""

from guidami_ai_patente.api.schemas.quiz_answers import (
    TopicMasteryResponse,
    UserStatisticsResponse,
)
from guidami_ai_patente.models import UserStatistics


class UserStatisticsMapper:
    """Turns a `UserStatistics` into the response the client receives. Static."""

    @staticmethod
    def from_statistics_to_response(statistics: UserStatistics) -> UserStatisticsResponse:
        """Builds the wire response, per-topic breakdown included."""
        return UserStatisticsResponse(
            answered=statistics.answered,
            seen=statistics.seen,
            bank_total=statistics.bank_total,
            mastered=statistics.mastered,
            in_review=statistics.in_review,
            topics=[
                TopicMasteryResponse(
                    topic=topic.topic,
                    seen=topic.seen,
                    mastered=topic.mastered,
                    total=topic.total,
                    insufficient_data=topic.insufficient_data,
                )
                for topic in statistics.topics
            ],
        )
