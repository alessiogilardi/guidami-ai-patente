from domain.entities.quiz import QuizMetadata
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel


def _question(**kwargs) -> EmbeddableQuizModel:
    defaults = dict(
        number="1",
        question_id=100,
        topic="Segnaletica",
        text="Il segnale raffigurato preavvisa un incrocio.",
        correct_answer=True,
    )
    return EmbeddableQuizModel(**{**defaults, **kwargs})


def _metadata(**kwargs) -> QuizMetadata:
    defaults = dict(
        core_concepts=["Obbligo di precedenza"],
        entities=["incrocio"],
        exact_keywords=["preavviso di incrocio"],
        vector_search_queries=["segnale preavviso incrocio", "obbligo precedenza incrocio"],
        rule_explanation="Il segnale preavvisa un incrocio regolato.",
    )
    return QuizMetadata(**{**defaults, **kwargs})


def test_embeddable_quiz_question_defaults_image_fields_to_none() -> None:
    q = _question()
    assert q.image_filename is None
    assert q.image_description is None
    assert q.embedding is None


def test_embedded_text_delegates_to_quiz_metadata_embedded_text() -> None:
    metadata = _metadata()
    q = _question(quiz_metadata=metadata)
    assert q.embedded_text == metadata.embedded_text
