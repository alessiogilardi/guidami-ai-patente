"""Tests for NormReferenceDescriberMapper (image sentinel, entities removal)."""

from guidami_ai_patente_ingestor.mappers.agents import NormReferenceDescriberMapper
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel


def _question(image_description: str | None = None) -> EnrichedQuizModel:
    return EnrichedQuizModel(
        question_id=1,
        topic="Segnaletica",
        number="1",
        text="Domanda.",
        correct_answer=True,
        image_description=image_description,
    )


def test_missing_image_maps_to_sentinel() -> None:
    question = _question(image_description=None)

    request = NormReferenceDescriberMapper.from_enriched_quiz_to_request(question)

    assert request.image_description == "Nessuna immagine allegata a questa domanda."
