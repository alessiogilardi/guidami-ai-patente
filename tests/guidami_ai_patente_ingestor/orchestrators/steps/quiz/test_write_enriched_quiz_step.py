"""Test per WriteEnrichedQuizStep."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import WriteEnrichedQuizStep
from guidami_ai_patente_ingestor.repositories import EnrichedQuizBankRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def test_required_keys_contains_enriched_quiz() -> None:
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    resolver = MagicMock(spec=LayerResolver)
    step = WriteEnrichedQuizStep("write_enriched_quiz", repo, resolver, "enriched", "quiz")
    assert step.get_required_keys() == {context_keys.ENRICHED_QUIZ}


def test_produced_keys_is_empty_set() -> None:
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    resolver = MagicMock(spec=LayerResolver)
    step = WriteEnrichedQuizStep("write_enriched_quiz", repo, resolver, "enriched", "quiz")
    assert step.get_produced_keys() == set()


def test_execute_writes_questions_to_resolved_path() -> None:
    questions = [MagicMock(spec=EnrichedQuizModel)]
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    expected_path = Path("/fake/enriched/quiz/quiz.json")
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.return_value = expected_path

    step = WriteEnrichedQuizStep("write_enriched_quiz", repo, resolver, "enriched", "quiz")
    context = FlowContext()
    context.put(context_keys.ENRICHED_QUIZ, questions)
    step.execute(context)

    resolver.path.assert_called_once_with("enriched", "quiz")
    repo.write.assert_called_once_with(questions, expected_path)
