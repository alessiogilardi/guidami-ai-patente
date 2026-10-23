"""UserStatisticsService combines history, bank topics and mastery into UserStatistics (FR-3)."""

from types import SimpleNamespace

import pytest

from guidami_ai_patente.models import AnsweredQuestion, TopicCount
from guidami_ai_patente.services import MasteryCalculator, UserStatisticsService

_TOPICS = [
    TopicCount(topic="precedenza", question_count=10),
    TopicCount(topic="segnaletica", question_count=20),
]


class _FakeAnswers:
    def __init__(self, history: list[AnsweredQuestion]) -> None:
        self.history = history
        self.calls: list[int] = []

    def user_history(self, telegram_user_id: int) -> list[AnsweredQuestion]:
        self.calls.append(telegram_user_id)
        return self.history


class _FakeQuestions:
    def list_topics(self) -> list[TopicCount]:
        return _TOPICS


def _answer(number: str, topic: str, correct: bool) -> AnsweredQuestion:
    return AnsweredQuestion(number=number, topic=topic, session_id="s", is_correct=correct)


def _resolve(history: list[AnsweredQuestion]) -> tuple[UserStatisticsService, _FakeAnswers]:
    # The repositories are already registered by their @repository decorators and pywire
    # cannot override a registration, so fields are assigned directly (as in
    # test_session_summary_service.py).
    answers = _FakeAnswers(history)
    calculator = object.__new__(MasteryCalculator)
    calculator.config = SimpleNamespace(review_exit_streak=2, topic_min_seen=2)  # type: ignore[assignment]
    service = object.__new__(UserStatisticsService)
    service.answers = answers  # type: ignore[assignment]
    service.questions = _FakeQuestions()  # type: ignore[assignment]
    service.mastery = calculator
    return service, answers


@pytest.mark.asyncio
async def test_seen_is_the_sum_of_mastered_and_in_review() -> None:
    service, answers = _resolve(
        [
            _answer("0001", "precedenza", True),
            _answer("0002", "precedenza", False),
            _answer("0002", "precedenza", True),
            _answer("0003", "segnaletica", False),
            _answer("0003", "segnaletica", False),
        ]
    )

    stats = await service(42)

    assert answers.calls == [42]
    assert stats.answered == 5
    assert stats.seen == 3
    assert stats.bank_total == 30
    assert stats.in_review == 2
    assert stats.mastered == 1
    assert stats.seen == stats.mastered + stats.in_review


@pytest.mark.asyncio
async def test_no_answers_yields_zeros_and_every_topic_insufficient() -> None:
    service, _ = _resolve([])

    stats = await service(42)

    assert (stats.answered, stats.seen, stats.mastered, stats.in_review) == (0, 0, 0, 0)
    assert stats.bank_total == 30
    assert {t.topic for t in stats.topics} == {"precedenza", "segnaletica"}
    assert all(t.insufficient_data for t in stats.topics)
