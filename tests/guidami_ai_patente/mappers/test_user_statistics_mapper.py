"""The wire response mirrors the user statistics field for field."""

from guidami_ai_patente.mappers import UserStatisticsMapper
from guidami_ai_patente.models import TopicMastery, UserStatistics


def test_the_response_carries_totals_and_topics() -> None:
    statistics = UserStatistics(
        answered=7,
        seen=4,
        bank_total=30,
        mastered=3,
        in_review=1,
        topics=[
            TopicMastery(
                topic="segnaletica", seen=4, mastered=3, total=20, insufficient_data=False
            )
        ],
    )

    response = UserStatisticsMapper.from_statistics_to_response(statistics)

    assert response.model_dump() == {
        "answered": 7,
        "seen": 4,
        "bank_total": 30,
        "mastered": 3,
        "in_review": 1,
        "topics": [
            {
                "topic": "segnaletica",
                "seen": 4,
                "mastered": 3,
                "total": 20,
                "insufficient_data": False,
            }
        ],
    }
