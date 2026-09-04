"""The proposal projection cannot carry the answer (spec 0012, AD-3)."""

from guidami_ai_patente.models import QuizQuestionSummary


def test_the_summary_has_no_correct_answer_field() -> None:
    assert "correct_answer" not in QuizQuestionSummary.model_fields, (
        "AD-3: excluding the answer is the only structural guarantee that grading is "
        "genuinely server-side"
    )


def test_an_image_less_question_carries_no_filename() -> None:
    summary = QuizQuestionSummary(
        number="0001", topic="segnaletica", text="Domanda?", image_filename=None
    )

    assert summary.image_filename is None
