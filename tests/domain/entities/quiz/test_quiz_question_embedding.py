from domain.entities.quiz import QuizQuestionEmbeddingEntity


def test_construct() -> None:
    result = QuizQuestionEmbeddingEntity(
        quiz_question_id=1, variant="text", embedding_3_small=[0.1, 0.2]
    )

    assert result.quiz_question_id == 1
    assert result.variant == "text"
    assert result.embedding_3_small == [0.1, 0.2]
