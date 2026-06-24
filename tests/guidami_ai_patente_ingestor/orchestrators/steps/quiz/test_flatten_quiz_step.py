"""Test per FlattenQuizStep (SP09: parsed nested → cleaned flat, flatten+dedup)."""

from unittest.mock import MagicMock, patch

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import FlattenQuizStep


def _main_question(
    question_id: int, topic: str, sub_questions: list[ParsedQuizItemModel]
) -> ParsedQuizModel:
    return ParsedQuizModel(question_id=question_id, topic=topic, sub_questions=sub_questions)


def _sub_question(
    number: str, text: str, correct_answer: bool, image: str | None = None
) -> ParsedQuizItemModel:
    return ParsedQuizItemModel(
        number=number, text=text, correct_answer=correct_answer, image=image
    )


def test_required_keys_contains_parsed_quiz() -> None:
    step = FlattenQuizStep("flatten_quiz")
    assert step.get_required_keys() == {context_keys.PARSED_QUIZ}


def test_produced_keys_contains_cleaned_quiz() -> None:
    step = FlattenQuizStep("flatten_quiz")
    assert step.get_produced_keys() == {context_keys.CLEANED_QUIZ}


def test_execute_delegates_to_quiz_mapper_for_each_kept_item() -> None:
    """Lo step chiama QuizMapper.from_parsed_to_cleaned per ogni item mantenuto."""
    main_question = _main_question(
        100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)]
    )
    context = FlowContext({context_keys.PARSED_QUIZ: [main_question]})
    cleaned_item = MagicMock(spec=CleanedQuizModel, number="1")

    with patch(
        "guidami_ai_patente_ingestor.orchestrators.steps.quiz.flatten_quiz_step"
        ".QuizMapper.from_parsed_to_cleaned",
        return_value=cleaned_item,
    ) as mock_mapper:
        step = FlattenQuizStep("flatten_quiz")
        step.execute(context)

        mock_mapper.assert_called_once_with(main_question.sub_questions[0], main_question)

    result = context.get(context_keys.CLEANED_QUIZ)
    assert result == [cleaned_item]


def test_execute_deduplicates_exact_duplicates_by_text_answer_and_image() -> None:
    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "  Domanda  ", correct_answer=True, image="img.jpeg"),
            _sub_question("2", "Domanda", correct_answer=True, image="img.jpeg"),
            _sub_question("3", "Altra domanda", correct_answer=False),
        ],
    )
    context = FlowContext({context_keys.PARSED_QUIZ: [main_question]})

    step = FlattenQuizStep("flatten_quiz")
    step.execute(context)

    result = context.get(context_keys.CLEANED_QUIZ)
    assert len(result) == 2
    assert result[0].number == "1"
    assert result[1].number == "3"


def test_execute_keeps_rows_with_same_text_but_different_image() -> None:
    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "Domanda", correct_answer=True, image="img-a.jpeg"),
            _sub_question("2", "Domanda", correct_answer=True, image="img-b.jpeg"),
        ],
    )
    context = FlowContext({context_keys.PARSED_QUIZ: [main_question]})

    step = FlattenQuizStep("flatten_quiz")
    step.execute(context)

    result = context.get(context_keys.CLEANED_QUIZ)
    assert len(result) == 2


def test_execute_keeps_rows_with_same_text_but_different_correct_answer() -> None:
    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "Domanda", correct_answer=True),
            _sub_question("2", "Domanda", correct_answer=False),
        ],
    )
    context = FlowContext({context_keys.PARSED_QUIZ: [main_question]})

    step = FlattenQuizStep("flatten_quiz")
    step.execute(context)

    result = context.get(context_keys.CLEANED_QUIZ)
    assert len(result) == 2
