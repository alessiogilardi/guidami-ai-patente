"""The wire response mirrors the session summary field for field, nested lists included."""

from guidami_ai_patente.mappers import SessionSummaryMapper
from guidami_ai_patente.models import SessionSummary, TopicSummary, WrongQuestion


def test_the_response_carries_totals_and_both_breakdowns() -> None:
    summary = SessionSummary(
        answered=3,
        correct=2,
        by_topic=[
            TopicSummary(topic="precedenza", answered=1, correct=1),
            TopicSummary(topic="segnaletica", answered=2, correct=1),
        ],
        wrong_questions=[WrongQuestion(number="0001", text="Il segnale vieta il sorpasso?")],
    )

    response = SessionSummaryMapper.from_summary_to_response(summary)

    assert response.model_dump() == {
        "answered": 3,
        "correct": 2,
        "by_topic": [
            {"topic": "precedenza", "answered": 1, "correct": 1},
            {"topic": "segnaletica", "answered": 2, "correct": 1},
        ],
        "wrong_questions": [{"number": "0001", "text": "Il segnale vieta il sorpasso?"}],
    }


def test_an_empty_summary_maps_to_empty_lists() -> None:
    summary = SessionSummary(answered=0, correct=0, by_topic=[], wrong_questions=[])

    response = SessionSummaryMapper.from_summary_to_response(summary)

    assert response.by_topic == []
    assert response.wrong_questions == []
