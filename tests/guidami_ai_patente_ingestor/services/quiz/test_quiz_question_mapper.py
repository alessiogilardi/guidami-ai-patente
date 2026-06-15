from guidami_ai_patente_ingestor.entities import QuizMainQuestion, QuizSubQuestion
from guidami_ai_patente_ingestor.services.quiz import QuizQuestionMapper


def _main_question(
    question_id: int, topic: str, sub_questions: list[QuizSubQuestion]
) -> QuizMainQuestion:
    return QuizMainQuestion(question_id=question_id, topic=topic, sub_questions=sub_questions)


def _sub_question(
    number: str, text: str, correct_answer: bool, image: str | None = None
) -> QuizSubQuestion:
    return QuizSubQuestion(number=number, text=text, correct_answer=correct_answer, image=image)


def test_map_denormalizes_question_id_and_topic_onto_each_row() -> None:
    main_questions = [
        _main_question(100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)])
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert len(questions) == 1
    assert questions[0].question_id == 100
    assert questions[0].topic == "Segnaletica"
    assert questions[0].number == "1"
    assert questions[0].text == "Domanda"
    assert questions[0].correct_answer is True


def test_map_extracts_image_filename_from_repo_relative_path() -> None:
    main_questions = [
        _main_question(
            100,
            "Segnaletica",
            [
                _sub_question(
                    "1",
                    "Domanda",
                    correct_answer=True,
                    image="data/processed/quiz-patente-ab/images/abc123.jpeg",
                )
            ],
        )
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert questions[0].image_filename == "abc123.jpeg"


def test_map_sets_image_filename_to_none_when_image_is_absent() -> None:
    main_questions = [
        _main_question(100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)])
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert questions[0].image_filename is None


def test_map_deduplicates_exact_duplicates_by_text_answer_and_image() -> None:
    main_questions = [
        _main_question(
            100,
            "Segnaletica",
            [
                _sub_question("1", "  Domanda  ", correct_answer=True, image="img.jpeg"),
                _sub_question("2", "Domanda", correct_answer=True, image="img.jpeg"),
            ],
        )
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert len(questions) == 1
    assert questions[0].number == "1"
    assert questions[0].text == "Domanda"


def test_map_keeps_rows_with_same_text_but_different_image() -> None:
    main_questions = [
        _main_question(
            100,
            "Segnaletica",
            [
                _sub_question("1", "Domanda", correct_answer=True, image="img-a.jpeg"),
                _sub_question("2", "Domanda", correct_answer=True, image="img-b.jpeg"),
            ],
        )
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert len(questions) == 2


def test_map_keeps_rows_with_same_text_but_different_correct_answer() -> None:
    main_questions = [
        _main_question(
            100,
            "Segnaletica",
            [
                _sub_question("1", "Domanda", correct_answer=True),
                _sub_question("2", "Domanda", correct_answer=False),
            ],
        )
    ]

    questions = QuizQuestionMapper().map(main_questions)

    assert len(questions) == 2
