"""ReviewQuestionService picks the next question to review (FR-4)."""

from types import SimpleNamespace

import pytest

from guidami_ai_patente.models import AnsweredQuestion, QuizQuestionSummary, ReviewRequest
from guidami_ai_patente.services import MasteryCalculator, ReviewQuestionService


class _FakeAnswers:
    def __init__(self, histories: dict[int, list[AnsweredQuestion]]) -> None:
        self.histories = histories

    def user_history(self, telegram_user_id: int) -> list[AnsweredQuestion]:
        return self.histories.get(telegram_user_id, [])


class _FakeQuestions:
    def find_by_number(self, number: str) -> QuizQuestionSummary | None:
        return QuizQuestionSummary(
            number=number, topic="t", text=f"q{number}", image_filename=None
        )


def _a(number: str, correct: bool, session: str = "old") -> AnsweredQuestion:
    return AnsweredQuestion(number=number, topic="t", session_id=session, is_correct=correct)


def _service(
    histories: dict[int, list[AnsweredQuestion]], max_repeats: int = 2
) -> ReviewQuestionService:
    # Fields assigned directly: the real beans are already registered by their decorators.
    config = SimpleNamespace(
        review_exit_streak=2, topic_min_seen=5, review_max_repeats_per_session=max_repeats
    )
    calculator = object.__new__(MasteryCalculator)
    calculator.config = config  # type: ignore[assignment]
    service = object.__new__(ReviewQuestionService)
    service.answers = _FakeAnswers(histories)  # type: ignore[assignment]
    service.questions = _FakeQuestions()  # type: ignore[assignment]
    service.mastery = calculator
    service.config = config  # type: ignore[assignment]
    return service


async def _next(service: ReviewQuestionService, session: str = "s1", user: int = 1) -> str | None:
    result = await service(ReviewRequest(telegram_user_id=user, session_id=session))
    return None if result is None else result.number


@pytest.mark.asyncio
async def test_lower_streak_is_served_before_higher_streak() -> None:
    history = [_a("B", False)] * 3 + [_a("B", True)] + [_a("A", False)]
    assert await _next(_service({1: history})) == "A"


@pytest.mark.asyncio
async def test_more_wrong_answers_first_at_equal_streak() -> None:
    history = [_a("D", False)] + [_a("C", False)] * 3
    assert await _next(_service({1: history})) == "C"


@pytest.mark.asyncio
async def test_order_is_stable_across_calls_with_the_same_session() -> None:
    history = [_a(n, False) for n in ("A", "B", "C", "D")]
    service = _service({1: history})
    assert len({await _next(service, "sx") for _ in range(5)}) == 1


@pytest.mark.asyncio
async def test_a_question_answered_correctly_in_session_is_not_served_again() -> None:
    history = [_a("A", False), _a("A", True, "s1")]
    assert await _next(_service({1: history})) is None


@pytest.mark.asyncio
async def test_unseen_questions_come_before_a_re_ask() -> None:
    history = [_a("A", False), _a("B", False), _a("B", False), _a("A", False, "s1")]
    service = _service({1: history})
    assert await _next(service) == "B"


@pytest.mark.asyncio
async def test_wrong_in_session_is_re_asked_once_unseen_are_exhausted() -> None:
    history = [_a("A", False, "s1")]
    assert await _next(_service({1: history})) == "A"


@pytest.mark.asyncio
async def test_wrong_three_times_in_session_is_never_served_again() -> None:
    history = [_a("A", False, "s1")] * 3
    assert await _next(_service({1: history})) is None


@pytest.mark.asyncio
async def test_no_in_review_questions_yields_none() -> None:
    assert await _next(_service({1: [_a("A", True), _a("A", True)]})) is None
    assert await _next(_service({})) is None


@pytest.mark.asyncio
async def test_zero_max_repeats_never_re_proposes_a_wrong_in_session_answer() -> None:
    history = [_a("A", False, "s1")]
    assert await _next(_service({1: history}, max_repeats=0)) is None


@pytest.mark.asyncio
async def test_oldest_wrong_in_session_answer_is_re_asked_first() -> None:
    history = [_a("A", False, "s1"), _a("B", False, "s1")]
    assert await _next(_service({1: history})) == "A"


@pytest.mark.asyncio
async def test_the_same_session_id_of_another_user_has_no_effect() -> None:
    history_x = [_a("A", False), _a("A", True, "s1")]
    history_y = [_a("A", False)]
    service = _service({1: history_x, 2: history_y})
    assert await _next(service, "s1", user=1) is None
    assert await _next(service, "s1", user=2) == "A"
