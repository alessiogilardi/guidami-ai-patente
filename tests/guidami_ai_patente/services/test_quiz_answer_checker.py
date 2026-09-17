"""QuizAnswerChecker sequences the answer lookup, persistence, and the status advertisement."""

from dataclasses import dataclass, field

import pytest

from guidami_ai_patente.enums import ExplanationStatus
from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.models import QuizAnswerCheckRequest
from guidami_ai_patente.services import QuizAnswerChecker


@dataclass
class _QuestionsDouble:
    correct_answer: bool | None

    def find_correct_answer(self, number: str) -> bool | None:
        return self.correct_answer


@dataclass
class _ExplanationStatusDouble:
    status: ExplanationStatus
    probes: list[str]

    def __call__(self, number: str) -> ExplanationStatus:
        self.probes.append(number)
        return self.status


@dataclass
class _AnswersDouble:
    calls: list[tuple[int, str, str, bool]] = field(default_factory=list)

    def record_answer(
        self, telegram_user_id: int, number: str, session_id: str, user_answer: bool
    ) -> None:
        self.calls.append((telegram_user_id, number, session_id, user_answer))


def _checker(
    correct_answer: bool | None, status: ExplanationStatus
) -> tuple[QuizAnswerChecker, _ExplanationStatusDouble, _AnswersDouble]:
    """Builds a `QuizAnswerChecker` wired to doubles, sidestepping pywire's container."""
    explanation_status = _ExplanationStatusDouble(status=status, probes=[])
    answers = _AnswersDouble()
    checker = object.__new__(QuizAnswerChecker)
    checker.questions = _QuestionsDouble(correct_answer)  # type: ignore[assignment]
    checker.explanation_status = explanation_status  # type: ignore[assignment]
    checker.answers = answers  # type: ignore[assignment]
    return checker, explanation_status, answers


def _request(number: str = "0001", submitted_answer: bool = True) -> QuizAnswerCheckRequest:
    return QuizAnswerCheckRequest(
        number=number,
        submitted_answer=submitted_answer,
        session_id="seed-abc",
        telegram_user_id=42,
    )


def test_a_correct_answer_is_graded_true() -> None:
    checker, _, _ = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    correct, _ = checker(_request(submitted_answer=True))

    assert correct is True


def test_a_wrong_answer_is_graded_false() -> None:
    checker, _, _ = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    correct, _ = checker(_request(submitted_answer=False))

    assert correct is False


def test_the_explanation_status_is_passed_through() -> None:
    checker, _, _ = _checker(correct_answer=True, status=ExplanationStatus.UNCACHED)

    _, status = checker(_request())

    assert status is ExplanationStatus.UNCACHED


def test_the_explanation_status_is_probed_with_the_requests_number() -> None:
    checker, explanation_status, _ = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    checker(_request(number="0042"))

    assert explanation_status.probes == ["0042"]


def test_an_unknown_number_raises_named() -> None:
    checker, _, _ = _checker(correct_answer=None, status=ExplanationStatus.UNAVAILABLE)

    with pytest.raises(QuestionNotFoundError, match="9999"):
        checker(_request(number="9999"))


def test_the_answer_is_recorded_with_the_callers_identity_and_session() -> None:
    checker, _, answers = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    checker(_request(number="0007", submitted_answer=False))

    assert answers.calls == [(42, "0007", "seed-abc", False)]


def test_an_unknown_number_records_no_answer() -> None:
    checker, _, answers = _checker(correct_answer=None, status=ExplanationStatus.UNAVAILABLE)

    with pytest.raises(QuestionNotFoundError):
        checker(_request(number="9999"))

    assert answers.calls == []
