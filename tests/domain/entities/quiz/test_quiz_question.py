from domain.entities.quiz import QuizQuestionEntity


def test_quiz_question_is_flat() -> None:
    """QuizQuestionEntity has the flat metadata columns and no nested quiz_metadata field."""
    fields = set(QuizQuestionEntity.model_fields)

    assert "quiz_metadata" not in fields
    assert {"core_concepts", "exact_keywords", "rule_explanation"} <= fields
    assert "named_entities" not in fields
