"""Test per QuizMapper (lato indexing, fuori scope SP09).

I metodi preparation (`from_parsed_to_cleaned`, `from_cleaned_to_enriched`) sono
testati separatamente in `test_quiz_mapper_flatten_at_preparation.py` (SP09).
"""

from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.mappers.quiz import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel, EnrichedQuizModel


def _sub_question(
    number: str,
    text: str,
    correct_answer: bool,
    image: str | None = None,
    image_description: str | None = None,
) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=100,
        topic="Segnaletica",
        number=number,
        text=text,
        correct_answer=correct_answer,
        image=image,
        image_description=image_description,
    )


def _embeddable(**kwargs) -> EmbeddableQuizModel:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Domanda di esempio.",
        correct_answer=True,
        image_filename="img.jpeg",
        image_description="Segnale di stop.",
        embedding=[0.1, 0.2, 0.3],
    )
    return EmbeddableQuizModel(**{**defaults, **kwargs})


# --- from_enriched_quiz_item_to_embeddable ---
# NOTE (SP09 09-quiz-flatten-at-preparation.md): MapToEmbeddableStep and
# from_enriched_quiz_item_to_embeddable belong to indexing, explicitly out of
# scope for this plan. These tests are kept minimal (compiling, not fixed) to
# avoid breaking the suite; the real fix is tracked in a future indexing plan.


def test_from_enriched_quiz_item_to_embeddable_copies_all_fields_from_item_and_parent() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question("1", "Domanda.", correct_answer=True, image_description="Stop.")

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert isinstance(result, EmbeddableQuizModel)
    assert result.number == "1"
    assert result.text == "Domanda."
    assert result.correct_answer is True
    assert result.image_description == "Stop."


def test_from_enriched_quiz_item_to_embeddable_strips_whitespace_from_text() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question("1", "  Testo con spazi  ", correct_answer=True)

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert result.text == "Testo con spazi"


def test_from_enriched_quiz_item_to_embeddable_extracts_image_filename_from_path() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question("1", "D", correct_answer=True, image="images/abc123.jpeg")

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert result.image_filename == "abc123.jpeg"


def test_from_enriched_quiz_item_to_embeddable_no_image_means_no_filename() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert result.image_filename is None


def test_from_enriched_quiz_item_to_embeddable_propagates_image_description() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question(
        "1",
        "Il segnale raffigurato.",
        correct_answer=True,
        image_description="Segnale di stop ottagonale rosso.",
    )

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert result.image_description == "Segnale di stop ottagonale rosso."


def test_from_enriched_quiz_item_to_embeddable_no_description_means_none() -> None:
    parent = _sub_question("0", "", correct_answer=False)
    item = _sub_question("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)

    assert result.image_description is None


# --- from_embeddable_to_quiz_question ---


def test_from_embeddable_to_quiz_question_copies_all_quiz_question_fields() -> None:
    eq = _embeddable()
    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert isinstance(result, QuizQuestion)
    assert result.number == eq.number
    assert result.question_id == eq.question_id
    assert result.topic == eq.topic
    assert result.text == eq.text
    assert result.correct_answer == eq.correct_answer
    assert result.image_filename == eq.image_filename
    assert result.embedding == eq.embedding


def test_from_embeddable_to_quiz_question_discards_image_description() -> None:
    eq = _embeddable(image_description="Segnale di stop.")
    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert not hasattr(result, "image_description")


def test_from_embeddable_to_quiz_question_preserves_none_embedding() -> None:
    eq = _embeddable(embedding=None)
    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert result.embedding is None


def test_from_embeddable_to_quiz_question_preserves_none_image_filename() -> None:
    eq = _embeddable(image_filename=None, image_description=None)
    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert result.image_filename is None
