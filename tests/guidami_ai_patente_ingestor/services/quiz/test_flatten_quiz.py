"""Test per FlattenQuiz (UseCase che appiattisce e deduplica il quiz bank parsed → cleaned)."""

from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)


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


def test_empty_input_returns_empty_list() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    flatten = FlattenQuiz()
    result = flatten([])
    assert result == []


def test_no_duplicates_all_preserved_and_mapped_to_cleaned_quiz_model() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "Prima domanda.", correct_answer=True),
            _sub_question("2", "Seconda domanda.", correct_answer=False),
        ],
    )
    flatten = FlattenQuiz()
    result = flatten([main_question])

    assert len(result) == 2
    assert all(isinstance(item, CleanedQuizModel) for item in result)


def test_duplicates_by_stripped_text_answer_image_are_deduplicated() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "  Domanda  ", correct_answer=True, image="img.jpeg"),
            _sub_question("2", "Domanda", correct_answer=True, image="img.jpeg"),
            _sub_question("3", "Altra domanda", correct_answer=False),
        ],
    )
    flatten = FlattenQuiz()
    result = flatten([main_question])

    assert len(result) == 2
    numbers = [item.number for item in result]
    assert "1" in numbers
    assert "3" in numbers
    assert "2" not in numbers


def test_same_text_different_image_both_kept() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "Domanda", correct_answer=True, image="img-a.jpeg"),
            _sub_question("2", "Domanda", correct_answer=True, image="img-b.jpeg"),
        ],
    )
    flatten = FlattenQuiz()
    result = flatten([main_question])

    assert len(result) == 2


def test_same_text_different_correct_answer_both_kept() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    main_question = _main_question(
        100,
        "Segnaletica",
        [
            _sub_question("1", "Domanda", correct_answer=True),
            _sub_question("2", "Domanda", correct_answer=False),
        ],
    )
    flatten = FlattenQuiz()
    result = flatten([main_question])

    assert len(result) == 2


def test_multiple_main_questions_all_sub_questions_flattened() -> None:
    from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz

    main_a = _main_question(
        100, "Segnaletica", [_sub_question("1", "Domanda A.", correct_answer=True)]
    )
    main_b = _main_question(
        200, "Precedenza", [_sub_question("2", "Domanda B.", correct_answer=False)]
    )
    flatten = FlattenQuiz()
    result = flatten([main_a, main_b])

    assert len(result) == 2
    assert result[0].question_id == 100
    assert result[1].question_id == 200
