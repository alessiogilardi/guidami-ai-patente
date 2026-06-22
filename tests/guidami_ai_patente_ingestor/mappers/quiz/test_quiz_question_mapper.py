from guidami_ai_patente_ingestor.mappers.quiz import QuizQuestionMapper
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizQuestion,
    EnrichedQuizMainQuestion,
    EnrichedQuizSubQuestion,
)

_map_one = QuizQuestionMapper.from_enriched_quiz_sub_question_to_embeddable_quiz_question
_map_many = QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions


def _main_question(
    question_id: int, topic: str, sub_questions: list[EnrichedQuizSubQuestion]
) -> EnrichedQuizMainQuestion:
    return EnrichedQuizMainQuestion(
        question_id=question_id, topic=topic, sub_questions=sub_questions
    )


def _sub_question(
    number: str,
    text: str,
    correct_answer: bool,
    image: str | None = None,
    image_description: str | None = None,
) -> EnrichedQuizSubQuestion:
    return EnrichedQuizSubQuestion(
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
        image_description=image_description,
    )


# --- from_enriched_quiz_sub_question_to_embeddable_quiz_question ---


def test_map_one_copies_all_fields_from_sub_and_parent() -> None:
    parent = _main_question(100, "Segnaletica", [])
    sub = _sub_question("1", "Domanda.", correct_answer=True, image_description="Stop.")

    result = _map_one(sub, parent)

    assert isinstance(result, EmbeddableQuizQuestion)
    assert result.number == "1"
    assert result.question_id == 100
    assert result.topic == "Segnaletica"
    assert result.text == "Domanda."
    assert result.correct_answer is True
    assert result.image_description == "Stop."


def test_map_one_strips_whitespace_from_text() -> None:
    parent = _main_question(1, "T", [])
    sub = _sub_question("1", "  Testo con spazi  ", correct_answer=True)

    result = _map_one(sub, parent)

    assert result.text == "Testo con spazi"


def test_map_one_extracts_image_filename_from_path() -> None:
    parent = _main_question(1, "T", [])
    sub = _sub_question("1", "D", correct_answer=True, image="images/abc123.jpeg")

    result = _map_one(sub, parent)

    assert result.image_filename == "abc123.jpeg"


def test_map_one_sets_image_filename_to_none_when_image_absent() -> None:
    parent = _main_question(1, "T", [])
    sub = _sub_question("1", "D", correct_answer=True)

    result = _map_one(sub, parent)

    assert result.image_filename is None


# --- from_enriched_quiz_main_questions_to_embeddable_quiz_questions ---


def test_map_many_denormalizes_question_id_and_topic_onto_each_row() -> None:
    main_questions = [
        _main_question(100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)])
    ]

    questions = _map_many(main_questions)

    assert len(questions) == 1
    assert isinstance(questions[0], EmbeddableQuizQuestion)
    assert questions[0].question_id == 100
    assert questions[0].topic == "Segnaletica"


def test_map_many_extracts_image_filename_from_repo_relative_path() -> None:
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

    questions = _map_many(main_questions)

    assert questions[0].image_filename == "abc123.jpeg"


def test_map_many_sets_image_filename_to_none_when_image_is_absent() -> None:
    main_questions = [
        _main_question(100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)])
    ]

    questions = _map_many(main_questions)

    assert questions[0].image_filename is None


def test_map_many_propagates_image_description_from_enriched_sub_question() -> None:
    main_questions = [
        _main_question(
            100,
            "Segnaletica",
            [
                _sub_question(
                    "1",
                    "Il segnale raffigurato.",
                    correct_answer=True,
                    image_description="Segnale di stop ottagonale rosso.",
                )
            ],
        )
    ]

    questions = _map_many(main_questions)

    assert questions[0].image_description == "Segnale di stop ottagonale rosso."


def test_map_many_sets_image_description_to_none_when_absent() -> None:
    main_questions = [
        _main_question(100, "Segnaletica", [_sub_question("1", "Domanda", correct_answer=True)])
    ]

    questions = _map_many(main_questions)

    assert questions[0].image_description is None


def test_map_many_deduplicates_exact_duplicates_by_text_answer_and_image() -> None:
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

    questions = _map_many(main_questions)

    assert len(questions) == 1
    assert questions[0].number == "1"
    assert questions[0].text == "Domanda"


def test_map_many_keeps_rows_with_same_text_but_different_image() -> None:
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

    questions = _map_many(main_questions)

    assert len(questions) == 2


def test_map_many_keeps_rows_with_same_text_but_different_correct_answer() -> None:
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

    questions = _map_many(main_questions)

    assert len(questions) == 2
