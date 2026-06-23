"""Test per MapToEmbeddableStep."""

from unittest.mock import MagicMock, patch

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import (
    EmbeddableQuizModel,
    EnrichedQuizModel,
)
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import MapToEmbeddableStep


def _make_main_question(question_id: int) -> EnrichedQuizModel:
    return MagicMock(spec=EnrichedQuizModel, question_id=question_id)


def _make_embeddable(number: str) -> EmbeddableQuizModel:
    return MagicMock(spec=EmbeddableQuizModel, number=number)


def test_required_keys_contains_enriched_quiz() -> None:
    step = MapToEmbeddableStep("map_to_embeddable")
    assert step.get_required_keys() == {context_keys.ENRICHED_QUIZ}


def test_produced_keys_contains_embeddable_quiz() -> None:
    step = MapToEmbeddableStep("map_to_embeddable")
    assert step.get_produced_keys() == {context_keys.EMBEDDABLE_QUIZ}


def test_execute_delegates_to_quiz_question_mapper() -> None:
    """Lo step delega al mapper statico e scrive il risultato in EMBEDDABLE_QUIZ."""
    main_questions = [_make_main_question(1), _make_main_question(2)]
    embeddable_questions = [_make_embeddable("001"), _make_embeddable("002")]

    context = FlowContext({context_keys.ENRICHED_QUIZ: main_questions})

    with patch(
        "guidami_ai_patente_ingestor.orchestrators.steps.quiz.map_to_embeddable_step"
        ".QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions",
        return_value=embeddable_questions,
    ) as mock_mapper:
        step = MapToEmbeddableStep("map_to_embeddable")
        step.execute(context)

        mock_mapper.assert_called_once_with(main_questions)

    result = context.get(context_keys.EMBEDDABLE_QUIZ)
    assert result is embeddable_questions


def test_execute_produces_correct_number_of_embeddable_items() -> None:
    """Verifica che lo step non filtri né duplchi gli item restituiti dal mapper."""
    embeddable_questions = [_make_embeddable(str(i)) for i in range(5)]
    main_questions: list[EnrichedQuizModel] = []

    context = FlowContext({context_keys.ENRICHED_QUIZ: main_questions})

    with patch(
        "guidami_ai_patente_ingestor.orchestrators.steps.quiz.map_to_embeddable_step"
        ".QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions",
        return_value=embeddable_questions,
    ):
        step = MapToEmbeddableStep("map_to_embeddable")
        step.execute(context)

    result = context.get(context_keys.EMBEDDABLE_QUIZ)
    assert len(result) == 5
