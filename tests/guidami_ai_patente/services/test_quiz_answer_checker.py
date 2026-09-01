"""QuizAnswerChecker sequences the answer lookup and the status advertisement."""

from dataclasses import dataclass

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


def _checker(
    correct_answer: bool | None, status: ExplanationStatus
) -> tuple[QuizAnswerChecker, _ExplanationStatusDouble]:
    """Builds a `QuizAnswerChecker` wired to doubles, sidestepping pywire's container.

    `object.__new__` sidesteps pywire's instrumented `__init__` — the class has no
    constructor body of its own, so setting the two fields is the whole of construction.
    """
    explanation_status = _ExplanationStatusDouble(status=status, probes=[])
    checker = object.__new__(QuizAnswerChecker)
    checker.questions = _QuestionsDouble(correct_answer)  # type: ignore[assignment]
    checker.explanation_status = explanation_status  # type: ignore[assignment]
    return checker, explanation_status


def test_a_correct_answer_is_graded_true() -> None:
    checker, _ = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    correct, _ = checker(QuizAnswerCheckRequest(number="0001", submitted_answer=True))

    assert correct is True


def test_a_wrong_answer_is_graded_false() -> None:
    checker, _ = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    correct, _ = checker(QuizAnswerCheckRequest(number="0001", submitted_answer=False))

    assert correct is False


def test_the_explanation_status_is_passed_through() -> None:
    checker, _ = _checker(correct_answer=True, status=ExplanationStatus.UNCACHED)

    _, status = checker(QuizAnswerCheckRequest(number="0001", submitted_answer=True))

    assert status is ExplanationStatus.UNCACHED


def test_the_explanation_status_is_probed_with_the_requests_number() -> None:
    checker, explanation_status = _checker(correct_answer=True, status=ExplanationStatus.CACHED)

    checker(QuizAnswerCheckRequest(number="0042", submitted_answer=True))

    assert explanation_status.probes == ["0042"]


def test_an_unknown_number_raises_named() -> None:
    checker, _ = _checker(correct_answer=None, status=ExplanationStatus.UNAVAILABLE)

    with pytest.raises(QuestionNotFoundError, match="9999"):
        checker(QuizAnswerCheckRequest(number="9999", submitted_answer=True))
