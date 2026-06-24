"""Test per QuizEnrichmentService."""

from unittest.mock import MagicMock

from guidami_ai_patente_ingestor.models.quiz import CleanedQuizModel, EnrichedQuizModel
from guidami_ai_patente_ingestor.services.quiz import QuizEnrichmentService
from guidami_ai_patente_ingestor.services.quiz.enrichers import QuizEnricher


def _cleaned_question(question_id: int) -> CleanedQuizModel:
    return CleanedQuizModel(
        question_id=question_id,
        topic="Segnaletica",
        number="1",
        text="Domanda.",
        correct_answer=True,
    )


def _identity_enricher() -> QuizEnricher:
    enricher = MagicMock(spec=QuizEnricher)
    enricher.enrich.side_effect = lambda questions: questions
    return enricher


def test_enrich_with_no_enrichers_returns_base_map_only() -> None:
    service = QuizEnrichmentService([])
    questions = [_cleaned_question(1)]

    result = service.enrich(questions)

    assert len(result) == 1
    assert isinstance(result[0], EnrichedQuizModel)
    assert result[0].question_id == 1
    assert result[0].image_description is None


def test_enrich_applies_each_enricher_in_order() -> None:
    first = MagicMock(spec=QuizEnricher)
    second = MagicMock(spec=QuizEnricher)
    intermediate = [MagicMock(spec=EnrichedQuizModel)]
    final = [MagicMock(spec=EnrichedQuizModel)]
    first.enrich.return_value = intermediate
    second.enrich.return_value = final

    service = QuizEnrichmentService([first, second])
    result = service.enrich([_cleaned_question(1)])

    first.enrich.assert_called_once()
    second.enrich.assert_called_once_with(intermediate)
    assert result == final
