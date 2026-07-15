"""Tests for QuizMapper (indexing side, out of scope for SP09).

The preparation methods (`from_parsed_to_cleaned`, `from_cleaned_to_enriched`) are
tested separately in `test_quiz_mapper_flatten_at_preparation.py` (SP09).
"""

from domain.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.mappers import QuizMapper
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizModel,
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


def _metadata(**kwargs) -> QuizMetadata:
    defaults = dict(
        core_concepts=["Obbligo di precedenza"],
        exact_keywords=["obbligo di precedenza"],
        vector_search_queries=["prima query di ricerca", "seconda query di ricerca"],
        rule_explanation="Il segnale impone l'obbligo di precedenza.",
    )
    return QuizMetadata(**{**defaults, **kwargs})


# --- from_enriched_to_embeddable ---


def test_from_enriched_to_embeddable_copies_all_fields() -> None:
    item = _enriched_item("1", "Domanda.", correct_answer=True, image_description="Stop.")

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert isinstance(result, EmbeddableQuizModel)
    assert result.number == "1"
    assert result.question_id == 100
    assert result.topic == "Segnaletica"
    assert result.text == "Domanda."
    assert result.correct_answer is True
    assert result.image_description == "Stop."


def test_from_enriched_to_embeddable_strips_whitespace_from_text() -> None:
    item = _enriched_item("1", "  Testo con spazi  ", correct_answer=True)

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert result.text == "Testo con spazi"


def test_from_enriched_to_embeddable_copies_image_filename() -> None:
    item = _enriched_item("1", "D", correct_answer=True, image="abc123.jpeg")

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert result.image_filename == "abc123.jpeg"


def test_from_enriched_to_embeddable_no_image_means_no_filename() -> None:
    item = _enriched_item("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert result.image_filename is None


def test_from_enriched_to_embeddable_propagates_image_description() -> None:
    item = _enriched_item(
        "1",
        "Il segnale raffigurato.",
        correct_answer=True,
        image_description="Segnale di stop ottagonale rosso.",
    )

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert result.image_description == "Segnale di stop ottagonale rosso."


def test_from_enriched_to_embeddable_no_description_means_none() -> None:
    item = _enriched_item("1", "D", correct_answer=True)

    result = QuizMapper.from_enriched_to_embeddable(item)

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


# --- quiz_metadata pass-through (from_enriched_to_embeddable keeps the nested model) ---


def test_from_enriched_to_embeddable_propagates_quiz_metadata() -> None:
    item = _enriched_item("1")
    # Inject quiz_metadata onto EnrichedQuizModel bypassing Pydantic validation to simulate
    # the state after the quiz_metadata field is declared on the model.
    sentinel = object()
    item.__dict__["quiz_metadata"] = sentinel

    result = QuizMapper.from_enriched_to_embeddable(item)

    assert getattr(result, "quiz_metadata", "MISSING") is sentinel, (
        "from_enriched_to_embeddable must propagate quiz_metadata to EmbeddableQuizModel"
    )


# --- from_embeddable_to_quiz_question flattens quiz_metadata onto the entity ---


def test_from_embeddable_to_quiz_question_spreads_metadata_into_flat_fields() -> None:
    metadata = _metadata()
    eq = _embeddable(quiz_metadata=metadata)

    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert result.core_concepts == metadata.core_concepts
    assert result.exact_keywords == metadata.exact_keywords
    assert result.rule_explanation == metadata.rule_explanation
    assert not hasattr(result, "named_entities")


def test_from_embeddable_to_quiz_question_drops_vector_search_queries() -> None:
    eq = _embeddable(quiz_metadata=_metadata())

    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert not hasattr(result, "vector_search_queries")


def test_from_embeddable_to_quiz_question_no_metadata_yields_none_fields() -> None:
    eq = _embeddable(quiz_metadata=None)

    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert result.core_concepts is None
    assert result.exact_keywords is None
    assert result.rule_explanation is None


def test_from_embeddable_to_quiz_question_has_no_nested_quiz_metadata() -> None:
    eq = _embeddable(quiz_metadata=_metadata())

    result = QuizMapper.from_embeddable_to_quiz_question(eq)

    assert not hasattr(result, "quiz_metadata")
