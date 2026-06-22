from commons.entities.quiz import QuizQuestion
from guidami_ai_patente_ingestor.mappers.quiz import EmbeddableQuizQuestionMapper
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizQuestion


def _embeddable(**kwargs) -> EmbeddableQuizQuestion:
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
    return EmbeddableQuizQuestion(**{**defaults, **kwargs})


def test_to_entity_copies_all_quiz_question_fields() -> None:
    eq = _embeddable()
    result = EmbeddableQuizQuestionMapper.to_entity(eq)

    assert isinstance(result, QuizQuestion)
    assert result.number == eq.number
    assert result.question_id == eq.question_id
    assert result.topic == eq.topic
    assert result.text == eq.text
    assert result.correct_answer == eq.correct_answer
    assert result.image_filename == eq.image_filename
    assert result.embedding == eq.embedding


def test_to_entity_discards_image_description() -> None:
    eq = _embeddable(image_description="Segnale di stop.")
    result = EmbeddableQuizQuestionMapper.to_entity(eq)

    assert not hasattr(result, "image_description")


def test_to_entity_preserves_none_embedding() -> None:
    eq = _embeddable(embedding=None)
    result = EmbeddableQuizQuestionMapper.to_entity(eq)

    assert result.embedding is None


def test_to_entity_preserves_none_image_filename() -> None:
    eq = _embeddable(image_filename=None, image_description=None)
    result = EmbeddableQuizQuestionMapper.to_entity(eq)

    assert result.image_filename is None
