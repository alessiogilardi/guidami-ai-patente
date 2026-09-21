"""The /stop summary is rendered as a structured, emoji-marked plain-text message."""

from guidami_ai_patente_bot import messages
from guidami_ai_patente_bot.models import SessionSummary, TopicSummary, WrongQuestion


def _summary(
    answered: int,
    correct: int,
    by_topic: list[TopicSummary] | None = None,
    wrong_questions: list[WrongQuestion] | None = None,
) -> SessionSummary:
    return SessionSummary(
        answered=answered,
        correct=correct,
        by_topic=by_topic or [],
        wrong_questions=wrong_questions or [],
    )


def test_a_session_with_no_answers_says_so_instead_of_showing_statistics() -> None:
    text = messages.summary_message(_summary(0, 0))

    assert text == messages.EMPTY_SUMMARY_MESSAGE


def test_the_header_shows_totals_and_the_percentage_of_correct_answers() -> None:
    text = messages.summary_message(_summary(12, 9))

    assert "12 domande · 9 corrette · 3 sbagliate (75%)" in text


def test_the_counts_use_the_singular_when_they_are_one() -> None:
    text = messages.summary_message(_summary(1, 1))

    assert "1 domanda · 1 corretta · 0 sbagliate (100%)" in text


def test_the_progress_bar_scales_correct_answers_to_ten_cells() -> None:
    text = messages.summary_message(_summary(5, 4))

    assert "🟩" * 8 + "🟥" * 2 in text


def test_the_progress_bar_is_all_green_when_everything_is_correct() -> None:
    text = messages.summary_message(_summary(3, 3))

    assert "🟩" * 10 in text
    assert "🟥" not in text


def test_the_progress_bar_is_all_red_when_nothing_is_correct() -> None:
    text = messages.summary_message(_summary(3, 0))

    assert "🟥" * 10 in text
    assert "🟩" not in text


def test_each_topic_is_listed_with_its_correct_over_answered_count() -> None:
    by_topic = [
        TopicSummary(topic="Precedenza", answered=3, correct=2),
        TopicSummary(topic="Segnali di pericolo", answered=4, correct=4),
    ]

    text = messages.summary_message(_summary(7, 6, by_topic=by_topic))

    assert "Per argomento:" in text
    assert "• Precedenza: 2/3" in text
    assert "• Segnali di pericolo: 4/4" in text


def test_a_topic_is_shortened_to_its_first_clause() -> None:
    """Official topic names chain many clauses with `;` and run past 300 characters."""
    topic = "Ingombro della carreggiata; segnalazione di veicolo fermo; traino dei rimorchi"
    by_topic = [TopicSummary(topic=topic, answered=1, correct=1)]

    text = messages.summary_message(_summary(1, 1, by_topic=by_topic))

    assert "• Ingombro della carreggiata: 1/1" in text
    assert "segnalazione" not in text


def test_a_single_overlong_topic_clause_is_truncated_with_an_ellipsis() -> None:
    by_topic = [TopicSummary(topic="A" * 100, answered=1, correct=0)]

    text = messages.summary_message(_summary(1, 0, by_topic=by_topic))

    topic_line = next(line for line in text.splitlines() if line.startswith("• A"))
    assert topic_line == f"• {'A' * 39}…: 0/1"


def test_the_topic_section_is_omitted_when_there_is_no_breakdown() -> None:
    text = messages.summary_message(_summary(2, 1))

    assert "Per argomento:" not in text


def test_wrong_questions_are_listed_with_their_text_truncated() -> None:
    long_text = (
        "Il conducente che intende svoltare a sinistra deve dare la precedenza a chi arriva"
    )
    wrong = [
        WrongQuestion(number="0001", text="Domanda breve?"),
        WrongQuestion(number="0002", text=long_text),
    ]

    text = messages.summary_message(_summary(4, 2, wrong_questions=wrong))

    assert "Da ripassare:" in text
    assert "• Domanda breve?" in text
    assert f"• {long_text[:59]}…" in text
    assert long_text not in text


def test_only_the_first_five_wrong_questions_are_shown_with_a_count_of_the_rest() -> None:
    wrong = [WrongQuestion(number=f"{n:04d}", text=f"Domanda {n}?") for n in range(1, 9)]

    text = messages.summary_message(_summary(8, 0, wrong_questions=wrong))

    assert "• Domanda 5?" in text
    assert "• Domanda 6?" not in text
    assert "…e altre 3" in text


def test_the_review_section_is_omitted_when_nothing_was_answered_wrongly() -> None:
    text = messages.summary_message(_summary(2, 2))

    assert "Da ripassare:" not in text
