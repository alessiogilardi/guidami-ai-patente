"""Tests for QuizMapper (indexing side, out of scope for SP09).

The preparation methods (`from_parsed_to_cleaned`, `from_cleaned_to_enriched`) are
tested separately in `test_quiz_mapper_flatten_at_preparation.py` (SP09).
"""

from domain.entities.quiz import QuizImageEntity, QuizQuestionEntity
from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddedQuizModel,
    EnrichedQuizModel,
    QuizMetadata,
)


def _enriched_item(
    number: str,
    text: str = "Domanda di esempio.",
    correct_answer: bool = True,
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


def _embedded(**kwargs) -> EmbeddedQuizModel:
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
    return EmbeddedQuizModel(**{**defaults, **kwargs})


def _metadata(**kwargs) -> QuizMetadata:
    defaults = dict(
        core_concepts=["Obbligo di precedenza"],
        exact_keywords=["obbligo di precedenza"],
        vector_search_queries=["prima query di ricerca", "seconda query di ricerca"],
        rule_explanation="Il segnale impone l'obbligo di precedenza.",
    )
    return QuizMetadata(**{**defaults, **kwargs})


# --- from_enriched_to_embedded ---


def test_from_enriched_to_embedded_copies_all_fields() -> None:
    item = _enriched_item("1", "Domanda.", correct_answer=True, image_description="Stop.")

    result = QuizMapper.from_enriched_to_embedded(item)

    assert isinstance(result, EmbeddedQuizModel)
    assert result.number == "1"
    assert result.question_id == 100
    assert result.topic == "Segnaletica"
    assert result.text == "Domanda."
    assert result.correct_answer is True
    assert result.image_description == "Stop."


def test_from_enriched_to_embedded_strips_whitespace_from_text() -> None:
    item = _enriched_item("1", "  Testo con spazi  ", correct_answer=True)

    result = QuizMapper.from_enriched_to_embedded(item)

    assert result.text == "Testo con spazi"


def test_from_enriched_to_embedded_copies_image_filename() -> None:
    item = _enriched_item("1", "D", correct_answer=True, image="abc123.jpeg")

    result = QuizMapper.from_enriched_to_embedded(item)

    assert result.image_filename == "abc123.jpeg"


def test_from_enriched_to_embedded_no_image_means_no_filename() -> None:
    item = _enriched_item("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_to_embedded(item)

    assert result.image_filename is None


def test_from_enriched_to_embedded_propagates_image_description() -> None:
    item = _enriched_item(
        "1",
        "Il segnale raffigurato.",
        correct_answer=True,
        image_description="Segnale di stop ottagonale rosso.",
    )

    result = QuizMapper.from_enriched_to_embedded(item)

    assert result.image_description == "Segnale di stop ottagonale rosso."


def test_from_enriched_to_embedded_no_description_means_none() -> None:
    item = _enriched_item("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_to_embedded(item)

    assert result.image_description is None


# --- from_embedded_to_quiz_question ---


def test_from_embedded_to_quiz_question_copies_all_quiz_question_fields() -> None:
    eq = _embedded()
    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert isinstance(result, QuizQuestionEntity)
    assert result.number == eq.number
    assert result.question_id == eq.question_id
    assert result.topic == eq.topic
    assert result.text == eq.text
    assert result.correct_answer == eq.correct_answer
    assert result.image_filename == eq.image_filename


def test_from_embedded_to_quiz_question_discards_image_description() -> None:
    eq = _embedded(image_description="Segnale di stop.")
    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert not hasattr(result, "image_description")


def test_from_embedded_to_quiz_question_preserves_none_image_filename() -> None:
    eq = _embedded(image_filename=None, image_description=None)
    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert result.image_filename is None


# --- quiz_metadata pass-through (from_enriched_to_embedded keeps the nested model) ---


def test_from_enriched_to_embedded_propagates_quiz_metadata() -> None:
    item = _enriched_item("1")
    # Inject quiz_metadata onto EnrichedQuizModel bypassing Pydantic validation to simulate
    # the state after the quiz_metadata field is declared on the model.
    sentinel = object()
    item.__dict__["quiz_metadata"] = sentinel

    result = QuizMapper.from_enriched_to_embedded(item)

    assert getattr(result, "quiz_metadata", "MISSING") is sentinel, (
        "from_enriched_to_embedded must propagate quiz_metadata to EmbeddedQuizModel"
    )


# --- from_embedded_to_quiz_question flattens quiz_metadata onto the entity ---


def test_from_embedded_to_quiz_question_spreads_metadata_into_flat_fields() -> None:
    metadata = _metadata()
    eq = _embedded(quiz_metadata=metadata)

    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert result.core_concepts == metadata.core_concepts
    assert result.exact_keywords == metadata.exact_keywords
    assert result.rule_explanation == metadata.rule_explanation
    assert not hasattr(result, "named_entities")


def test_from_embedded_to_quiz_question_persists_vector_search_queries() -> None:
    metadata = _metadata()
    eq = _embedded(quiz_metadata=metadata)

    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert result.vector_search_queries == metadata.vector_search_queries


def test_from_embedded_to_quiz_question_no_metadata_yields_none_fields() -> None:
    eq = _embedded(quiz_metadata=None)

    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert result.core_concepts is None
    assert result.exact_keywords is None
    assert result.rule_explanation is None


def test_from_embedded_to_quiz_question_no_metadata_yields_none_vector_search_queries() -> None:
    eq = _embedded(quiz_metadata=None)

    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert result.vector_search_queries is None


def test_from_embedded_to_quiz_question_has_no_nested_quiz_metadata() -> None:
    eq = _embedded(quiz_metadata=_metadata())

    result = QuizMapper.from_embedded_to_quiz_question(eq)

    assert not hasattr(result, "quiz_metadata")


# --- from_embedded_to_quiz_images ---


def test_from_embedded_to_quiz_images_returns_one_entity_when_image_present() -> None:
    eq = _embedded()

    result = QuizMapper.from_embedded_to_quiz_images(eq)

    assert result == [QuizImageEntity(filename="img.jpeg", description="Segnale di stop.")]


def test_from_embedded_to_quiz_images_returns_empty_list_when_no_image() -> None:
    eq = _embedded(image_filename=None, image_description=None)

    result = QuizMapper.from_embedded_to_quiz_images(eq)

    assert result == []
