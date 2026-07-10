"""Test per i nuovi metodi QuizMapper introdotti da SP09 (flatten anticipato a preparation).

`from_cleaned_to_enriched` (flat->flat base-map), `from_parsed_to_cleaned`
(nested item -> flat, denormalizza question_id/topic dal genitore) e
`from_parsed_to_cleaned_all` (unnest+map di una domanda parsed intera,
collassato da FlattenQuiz, vedi docs/plans/2026-07-09--collapse-flatten-quiz-into-flatmap.md).
"""

from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    CleanedQuizModel,
    EnrichedQuizModel,
    ParsedQuizItemModel,
    ParsedQuizModel,
)


def _cleaned_item(**kwargs) -> CleanedQuizModel:
    defaults = dict(
        question_id=100,
        topic="Segnaletica",
        number="1",
        text="Domanda di esempio.",
        correct_answer=True,
        image="img.jpeg",
    )
    return CleanedQuizModel(**{**defaults, **kwargs})


def _parsed_item(**kwargs) -> ParsedQuizItemModel:
    defaults = dict(number="1", text="Domanda.", correct_answer=True, image=None)
    return ParsedQuizItemModel(**{**defaults, **kwargs})


def _parsed_question(**kwargs) -> ParsedQuizModel:
    defaults = dict(question_id=100, topic="Segnaletica", sub_questions=[])
    return ParsedQuizModel(**{**defaults, **kwargs})


# --- from_cleaned_to_enriched ---


def test_from_cleaned_to_enriched_copies_all_flat_fields() -> None:
    item = _cleaned_item()

    result = QuizMapper.from_cleaned_to_enriched(item)

    assert isinstance(result, EnrichedQuizModel)
    assert result.question_id == item.question_id
    assert result.topic == item.topic
    assert result.number == item.number
    assert result.text == item.text
    assert result.correct_answer == item.correct_answer
    assert result.image == item.image


def test_from_cleaned_to_enriched_sets_image_description_to_none() -> None:
    item = _cleaned_item()

    result = QuizMapper.from_cleaned_to_enriched(item)

    assert result.image_description is None


# --- from_parsed_to_cleaned ---


def test_from_parsed_to_cleaned_denormalizes_question_id_and_topic_from_parent() -> None:
    parent = _parsed_question(question_id=100, topic="Segnaletica")
    item = _parsed_item(number="1", text="Domanda.", correct_answer=True)

    result = QuizMapper.from_parsed_to_cleaned(item, parent)

    assert isinstance(result, CleanedQuizModel)
    assert result.question_id == 100
    assert result.topic == "Segnaletica"
    assert result.number == "1"
    assert result.correct_answer is True


def test_from_parsed_to_cleaned_strips_whitespace_from_text() -> None:
    parent = _parsed_question()
    item = _parsed_item(text="  Testo con spazi  ")

    result = QuizMapper.from_parsed_to_cleaned(item, parent)

    assert result.text == "Testo con spazi"


def test_from_parsed_to_cleaned_propagates_image_path_unchanged() -> None:
    parent = _parsed_question()
    item = _parsed_item(image="images/sign.jpeg")

    result = QuizMapper.from_parsed_to_cleaned(item, parent)

    assert result.image == "images/sign.jpeg"


def test_from_parsed_to_cleaned_no_image_means_none() -> None:
    parent = _parsed_question()
    item = _parsed_item(image=None)

    result = QuizMapper.from_parsed_to_cleaned(item, parent)

    assert result.image is None


# --- from_parsed_to_cleaned_all ---


def test_from_parsed_to_cleaned_all_empty_sub_questions_returns_empty_list() -> None:
    parent = _parsed_question(sub_questions=[])

    result = QuizMapper.from_parsed_to_cleaned_all(parent)

    assert result == []


def test_from_parsed_to_cleaned_all_maps_every_sub_question_in_order() -> None:
    sub_1 = _parsed_item(number="1", text="Prima domanda.")
    sub_2 = _parsed_item(number="2", text="Seconda domanda.")
    parent = _parsed_question(question_id=100, topic="Segnaletica", sub_questions=[sub_1, sub_2])

    result = QuizMapper.from_parsed_to_cleaned_all(parent)

    assert [item.number for item in result] == ["1", "2"]
    assert [item.text for item in result] == ["Prima domanda.", "Seconda domanda."]


def test_from_parsed_to_cleaned_all_denormalizes_parent_question_id_and_topic() -> None:
    sub_1 = _parsed_item(number="1")
    sub_2 = _parsed_item(number="2")
    parent = _parsed_question(question_id=42, topic="Precedenza", sub_questions=[sub_1, sub_2])

    result = QuizMapper.from_parsed_to_cleaned_all(parent)

    assert all(isinstance(item, CleanedQuizModel) for item in result)
    assert all(item.question_id == 42 for item in result)
    assert all(item.topic == "Precedenza" for item in result)
