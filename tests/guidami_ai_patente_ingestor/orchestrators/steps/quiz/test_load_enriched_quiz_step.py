"""Test per LoadEnrichedQuizStep."""

from pathlib import Path
from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import EnrichedQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import LoadEnrichedQuizStep
from guidami_ai_patente_ingestor.repositories import EnrichedQuizBankRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/quiz.json")
    return resolver


def _make_main_question(question_id: int) -> EnrichedQuizModel:
    return MagicMock(spec=EnrichedQuizModel, question_id=question_id)


def test_required_keys_is_empty_set() -> None:
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedQuizStep("load_quiz", repo, resolver, input_layer="enriched", source="quiz")
    assert step.get_required_keys() == set()


def test_produced_keys_contains_enriched_quiz() -> None:
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    resolver = _make_layer_resolver()
    step = LoadEnrichedQuizStep("load_quiz", repo, resolver, input_layer="enriched", source="quiz")
    assert step.get_produced_keys() == {context_keys.ENRICHED_QUIZ}


def test_execute_loads_source_and_puts_list_in_context() -> None:
    questions = [_make_main_question(1), _make_main_question(2)]
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    repo.load.return_value = questions
    resolver = _make_layer_resolver()

    step = LoadEnrichedQuizStep("load_quiz", repo, resolver, input_layer="enriched", source="quiz")
    context = FlowContext()
    step.execute(context)

    result: list[EnrichedQuizModel] = context.get(context_keys.ENRICHED_QUIZ)
    assert result is questions


def test_execute_resolves_path_for_the_configured_source() -> None:
    """Lo step risolve il path usando la source iniettata, non una costante hardcoded."""
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    repo.load.return_value = []
    resolver = _make_layer_resolver()

    step = LoadEnrichedQuizStep("load_quiz", repo, resolver, input_layer="enriched", source="quiz")
    step.execute(FlowContext())

    resolver.path.assert_called_once_with("enriched", "quiz")


def test_execute_passes_resolved_path_to_repository() -> None:
    """Il path risolto dal resolver è quello passato al repository."""
    repo = MagicMock(spec=EnrichedQuizBankRepository)
    repo.load.return_value = []
    expected_path = Path("/fake/enriched/quiz/quiz.json")
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.return_value = expected_path

    step = LoadEnrichedQuizStep("load_quiz", repo, resolver, input_layer="enriched", source="quiz")
    step.execute(FlowContext())

    repo.load.assert_called_once_with(expected_path)
