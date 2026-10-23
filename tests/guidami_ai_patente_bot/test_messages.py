"""The /stop summary is rendered as a structured, emoji-marked plain-text message."""

from guidami_ai_patente_bot import messages
from guidami_ai_patente_bot.models import (
    SessionSummary,
    TopicMastery,
    TopicSummary,
    UserStatistics,
    WrongQuestion,
)


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


def _stats(
    topics: list[TopicMastery] | None = None,
    *,
    in_review: int = 0,
    bank_total: int = 100,
    seen: int = 10,
    mastered: int = 8,
) -> UserStatistics:
    return UserStatistics(
        answered=50,
        seen=seen,
        bank_total=bank_total,
        mastered=mastered,
        in_review=in_review,
        topics=topics or [],
    )


def _topic(name: str, *, seen: int, mastered: int, total: int, insufficient: bool) -> TopicMastery:
    return TopicMastery(
        topic=name, seen=seen, mastered=mastered, total=total, insufficient_data=insufficient
    )


def test_statistics_show_the_totals_line_with_seen_and_mastered_percentage() -> None:
    text = messages.statistics_message(_stats(), 40)

    assert "Domande viste: 10/100" in text
    assert "Padroneggiate: 8 (80%)" in text


def test_statistics_totals_line_with_an_empty_bank_reports_zero_total() -> None:
    text = messages.statistics_message(_stats(bank_total=0), 40)

    assert "Domande viste: 10/0" in text


def test_statistics_with_nothing_seen_show_zero_percent_mastered() -> None:
    text = messages.statistics_message(_stats(seen=0, mastered=0), 40)

    assert "Padroneggiate: 0 (0%)" in text


def test_ranked_topics_come_before_the_da_esplorare_header() -> None:
    topics = [
        _topic("Segnali; x", seen=10, mastered=8, total=20, insufficient=False),
        _topic("Precedenza; y", seen=1, mastered=0, total=15, insufficient=True),
    ]

    text = messages.statistics_message(_stats(topics), 40)

    assert "Segnali: 80%" in text
    assert text.index("Segnali") < text.index("Da esplorare") < text.index("Precedenza")
    assert "Precedenza: 1/15" in text


def test_the_da_esplorare_header_is_omitted_without_insufficient_topics() -> None:
    topics = [_topic("Segnali", seen=10, mastered=5, total=20, insufficient=False)]

    assert "Da esplorare" not in messages.statistics_message(_stats(topics), 40)


def test_the_review_hint_is_shown_only_when_there_are_questions_in_review() -> None:
    with_review = messages.statistics_message(_stats(in_review=3), 40)
    without_review = messages.statistics_message(_stats(in_review=0), 40)

    assert "/ripasso" in with_review
    assert "3 domande da ripassare" in with_review
    assert "/ripasso" not in without_review


def test_topic_label_keeps_the_text_before_the_first_semicolon() -> None:
    assert messages.topic_label("Segnali di pericolo; altro", 40) == "Segnali di pericolo"


def test_topic_label_truncates_a_long_first_segment_with_an_ellipsis() -> None:
    assert messages.topic_label("abcdefghijklmnop; x", 10) == "abcdefghi…"


def test_topic_label_falls_back_to_the_full_name_when_the_first_segment_is_empty() -> None:
    assert messages.topic_label("; Resto", 40) == "; Resto"


def test_topic_label_returns_the_whole_name_without_a_semicolon() -> None:
    assert messages.topic_label("Precedenza", 40) == "Precedenza"


def test_topic_button_label_shows_percent_for_ranked_and_seen_total_otherwise() -> None:
    ranked = TopicMastery(topic="Segnali; x", seen=4, mastered=2, total=9, insufficient_data=False)
    explore = TopicMastery(topic="Precedenza", seen=1, mastered=0, total=7, insufficient_data=True)
    assert messages.topic_button_label(ranked, 40) == "Segnali: 50%"
    assert messages.topic_button_label(explore, 40) == "Precedenza: 1/7"
