"""The wire projection carries an image URL, never a bare filename (AD-24)."""

from guidami_ai_patente.mappers import QuizQuestionMapper
from guidami_ai_patente.models import QuizQuestionSummary


def _summary(image_filename: str | None) -> QuizQuestionSummary:
    return QuizQuestionSummary(
        number="0001", topic="segnaletica", text="Domanda?", image_filename=image_filename
    )


def test_an_image_less_question_has_a_null_url() -> None:
    response = QuizQuestionMapper.from_summary_to_response(_summary(None))

    assert response.image_url is None


def test_an_illustrated_question_carries_the_endpoint_path() -> None:
    response = QuizQuestionMapper.from_summary_to_response(_summary("s0001.jpeg"))

    assert response.image_url == "/quiz-images/s0001.jpeg"


def test_the_response_never_carries_the_answer() -> None:
    from guidami_ai_patente.api.schemas.quiz_question import QuizQuestionResponse

    assert "correct_answer" not in QuizQuestionResponse.model_fields
