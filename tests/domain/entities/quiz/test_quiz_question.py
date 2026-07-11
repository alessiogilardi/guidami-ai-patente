from domain.entities.quiz import QuizQuestion


def test_quiz_question_is_flat() -> None:
    """QuizQuestion has the flat metadata columns and no nested quiz_metadata field."""
    fields = set(QuizQuestion.model_fields)

    assert "quiz_metadata" not in fields
    assert {"core_concepts", "named_entities", "exact_keywords", "rule_explanation"} <= fields
