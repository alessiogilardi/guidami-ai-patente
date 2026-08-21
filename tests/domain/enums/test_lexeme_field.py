from domain.enums import LexemeField
from domain.models.retrieval import QuizEvaluationRow


def test_every_member_names_a_quiz_evaluation_row_field() -> None:
    for member in LexemeField:
        assert member.value in QuizEvaluationRow.model_fields
