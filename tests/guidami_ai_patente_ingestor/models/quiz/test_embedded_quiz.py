from guidami_ai_patente_ingestor.models.quiz import EmbeddedQuizModel


def _question(**kwargs) -> EmbeddedQuizModel:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Il segnale raffigurato preavvisa un incrocio.",
        correct_answer=True,
    )
    return EmbeddedQuizModel(**{**defaults, **kwargs})


def test_embedded_quiz_question_defaults_image_fields_to_none() -> None:
    q = _question()
    assert q.image_filename is None
    assert q.image_description is None
