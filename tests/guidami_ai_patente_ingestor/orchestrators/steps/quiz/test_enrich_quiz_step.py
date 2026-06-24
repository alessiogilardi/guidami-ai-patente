"""Test per EnrichQuizStep."""

from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import CleanedQuizModel, EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import EnrichQuizStep
from guidami_ai_patente_ingestor.services import QuizEnrichmentService


def test_required_keys_contains_cleaned_quiz() -> None:
    service = MagicMock(spec=QuizEnrichmentService)
    step = EnrichQuizStep("enrich_quiz", service)
    assert step.get_required_keys() == {context_keys.CLEANED_QUIZ}


def test_produced_keys_contains_enriched_quiz() -> None:
    service = MagicMock(spec=QuizEnrichmentService)
    step = EnrichQuizStep("enrich_quiz", service)
    assert step.get_produced_keys() == {context_keys.ENRICHED_QUIZ}


def test_execute_delegates_to_service_and_puts_result_in_context() -> None:
    questions = [MagicMock(spec=CleanedQuizModel)]
    enriched = [MagicMock(spec=EnrichedQuizModel)]
    service = MagicMock(spec=QuizEnrichmentService)
    service.enrich.return_value = enriched

    step = EnrichQuizStep("enrich_quiz", service)
    context = FlowContext()
    context.put(context_keys.CLEANED_QUIZ, questions)
    step.execute(context)

    service.enrich.assert_called_once_with(questions)
    assert context.get(context_keys.ENRICHED_QUIZ) is enriched
