"""Tests for FilterByImageStep (spec 0023, FR-4)."""

from typing import cast

import pytest
from flowstep import FlowContext

from guidami_ai_patente_ingestor.exceptions import UnknownImageError
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import FilterByImageStep


def _quiz(number: str, image: str | None) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=1,
        topic="Segnaletica",
        number=number,
        text=f"Domanda {number}.",
        correct_answer=True,
        image=image,
    )


def _run(images: list[str], quizzes: list[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
    step = FilterByImageStep("filter_quiz_by_image", "in", "out", images)
    context = FlowContext({"in": quizzes})
    step.execute(context)
    return cast(list[EnrichedQuizModel], context.get("out"))


def test_no_filter_keeps_every_quiz_with_an_image_and_drops_the_rest() -> None:
    quizzes = [_quiz("1", "a.jpeg"), _quiz("2", None), _quiz("3", "b.jpeg")]

    assert [q.number for q in _run([], quizzes)] == ["1", "3"]


def test_filter_keeps_every_quiz_of_the_named_images_so_contexts_stay_complete() -> None:
    quizzes = [_quiz("1", "a.jpeg"), _quiz("2", "a.jpeg"), _quiz("3", "b.jpeg")]

    assert [q.number for q in _run(["a.jpeg"], quizzes)] == ["1", "2"]


def test_repeated_image_name_is_harmless() -> None:
    quizzes = [_quiz("1", "a.jpeg"), _quiz("2", "b.jpeg")]

    assert [q.number for q in _run(["a.jpeg", "a.jpeg"], quizzes)] == ["1"]


def test_unknown_image_raises_and_lists_every_unknown_name() -> None:
    quizzes = [_quiz("1", "a.jpeg")]

    with pytest.raises(UnknownImageError) as excinfo:
        _run(["a.jpeg", "zzz.jpeg", "yyy.jpeg"], quizzes)

    assert excinfo.value.unknown == ("yyy.jpeg", "zzz.jpeg")
    assert "yyy.jpeg" in str(excinfo.value)
    assert "zzz.jpeg" in str(excinfo.value)


def test_step_declares_its_context_keys() -> None:
    step = FilterByImageStep("filter_quiz_by_image", "in", "out", [])

    assert step.get_required_keys() == {"in"}
    assert step.get_produced_keys() == {"out"}
