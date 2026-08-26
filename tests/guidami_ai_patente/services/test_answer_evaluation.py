"""The comparison itself is a stateless function (spec 0012, AD-17)."""

import pytest

from guidami_ai_patente.exceptions import QuestionNotFoundError
from guidami_ai_patente.services import evaluate_answer


def test_a_matching_answer_is_correct() -> None:
    assert evaluate_answer(True, True) is True
    assert evaluate_answer(False, False) is True


def test_a_differing_answer_is_incorrect() -> None:
    assert evaluate_answer(True, False) is False
    assert evaluate_answer(False, True) is False


def test_a_missing_question_raises_rather_than_grading() -> None:
    with pytest.raises(QuestionNotFoundError):
        evaluate_answer(None, True)
