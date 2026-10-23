"""Tests for the mastery models."""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.models import (
    AnsweredQuestion,
    QuestionMastery,
    ReviewRequest,
    TopicMastery,
    UserStatistics,
)


def _mastery(in_review: bool) -> QuestionMastery:
    return QuestionMastery(
        number="0001", topic="segnali", wrong_count=1, streak=0, in_review=in_review
    )


def test_question_in_review_is_not_mastered() -> None:
    assert _mastery(in_review=True).mastered is False


def test_question_not_in_review_is_mastered() -> None:
    assert _mastery(in_review=False).mastered is True


def test_models_reject_mutation() -> None:
    mastery = _mastery(in_review=False)
    answered = AnsweredQuestion(number="0001", topic="segnali", session_id="s", is_correct=True)
    topic = TopicMastery(topic="segnali", seen=1, mastered=1, total=2, insufficient_data=False)
    stats = UserStatistics(
        answered=1, seen=1, bank_total=2, mastered=1, in_review=0, topics=[topic]
    )
    request = ReviewRequest(telegram_user_id=1, session_id="s")

    for model, field, value in [
        (mastery, "streak", 5),
        (answered, "is_correct", False),
        (topic, "seen", 9),
        (stats, "answered", 9),
        (request, "session_id", "x"),
    ]:
        with pytest.raises(ValidationError):
            setattr(model, field, value)
