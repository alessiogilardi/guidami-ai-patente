"""Test per MapToQuizEntityStep."""

from unittest.mock import MagicMock, patch

from commons.entities.quiz import QuizQuestion
from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.models.quiz import EmbeddableQuizModel
from guidami_ai_patente_ingestor.orchestrators import context_keys
from guidami_ai_patente_ingestor.orchestrators.steps.quiz import MapToQuizEntityStep


def _make_embeddable(number: str) -> EmbeddableQuizModel:
    return MagicMock(spec=EmbeddableQuizModel, number=number)


def _make_quiz_question(number: str) -> QuizQuestion:
    return MagicMock(spec=QuizQuestion, number=number)


def test_required_keys_contains_embeddable_quiz() -> None:
    step = MapToQuizEntityStep("map_to_quiz_entity")
    assert step.get_required_keys() == {context_keys.EMBEDDABLE_QUIZ}


def test_produced_keys_contains_quiz_entities() -> None:
    step = MapToQuizEntityStep("map_to_quiz_entity")
    assert step.get_produced_keys() == {context_keys.QUIZ_ENTITIES}


def test_execute_delegates_to_embeddable_quiz_question_mapper() -> None:
    """Lo step chiama EmbeddableQuizQuestionMapper.to_entity per ogni item."""
    embeddables = [_make_embeddable("001"), _make_embeddable("002")]
    entities = [_make_quiz_question("001"), _make_quiz_question("002")]

    context = FlowContext({context_keys.EMBEDDABLE_QUIZ: embeddables})

    with patch(
        "guidami_ai_patente_ingestor.orchestrators.steps.quiz.map_to_quiz_entity_step"
        ".EmbeddableQuizQuestionMapper.to_entity",
        side_effect=entities,
    ) as mock_mapper:
        step = MapToQuizEntityStep("map_to_quiz_entity")
        step.execute(context)

        assert mock_mapper.call_count == 2
        mock_mapper.assert_any_call(embeddables[0])
        mock_mapper.assert_any_call(embeddables[1])

    result = context.get(context_keys.QUIZ_ENTITIES)
    assert result == entities


def test_execute_produces_entity_list_same_length_as_input() -> None:
    """Lo step non filtra né duplica: output len == input len."""
    embeddables = [_make_embeddable(str(i)) for i in range(3)]
    entities = [_make_quiz_question(str(i)) for i in range(3)]

    context = FlowContext({context_keys.EMBEDDABLE_QUIZ: embeddables})

    with patch(
        "guidami_ai_patente_ingestor.orchestrators.steps.quiz.map_to_quiz_entity_step"
        ".EmbeddableQuizQuestionMapper.to_entity",
        side_effect=entities,
    ):
        step = MapToQuizEntityStep("map_to_quiz_entity")
        step.execute(context)

    result = context.get(context_keys.QUIZ_ENTITIES)
    assert len(result) == 3
