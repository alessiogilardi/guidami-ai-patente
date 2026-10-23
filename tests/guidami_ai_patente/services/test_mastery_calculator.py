"""MasteryCalculator derives question and topic mastery from answer history (FR-1, FR-2)."""

from types import SimpleNamespace

import pytest

from guidami_ai_patente.models import AnsweredQuestion, TopicCount
from guidami_ai_patente.services import MasteryCalculator


@pytest.fixture
def calculator() -> MasteryCalculator:
    instance = object.__new__(MasteryCalculator)
    instance.config = SimpleNamespace(review_exit_streak=2, topic_min_seen=5)  # type: ignore[assignment]
    return instance


def _h(marks: str, number: str = "0001", topic: str = "T") -> list[AnsweredQuestion]:
    """Builds a history for one question: `✓` is a correct answer, `✗` a wrong one."""
    return [
        AnsweredQuestion(number=number, topic=topic, session_id="s", is_correct=mark == "✓")
        for mark in marks
    ]


def test_never_wrong_question_is_mastered(calculator: MasteryCalculator) -> None:
    state = calculator.question_states(_h("✓✓"))["0001"]

    assert state.mastered
    assert state.wrong_count == 0


def test_single_wrong_answer_puts_question_in_review(calculator: MasteryCalculator) -> None:
    state = calculator.question_states(_h("✗"))["0001"]

    assert state.in_review
    assert state.streak == 0
    assert state.wrong_count == 1


def test_one_correct_after_wrong_is_still_in_review(calculator: MasteryCalculator) -> None:
    state = calculator.question_states(_h("✗✓"))["0001"]

    assert state.in_review
    assert state.streak == 1


def test_exit_streak_correct_answers_leave_review(calculator: MasteryCalculator) -> None:
    state = calculator.question_states(_h("✗✓✓"))["0001"]

    assert not state.in_review
    assert state.streak == 2
    assert state.wrong_count == 1


def test_a_new_wrong_answer_resets_the_streak(calculator: MasteryCalculator) -> None:
    state = calculator.question_states(_h("✗✓✗"))["0001"]

    assert state.in_review
    assert state.streak == 0
    assert state.wrong_count == 2


def test_wrong_then_many_correct_counts_the_question_once(calculator: MasteryCalculator) -> None:
    states = calculator.question_states(_h("✗" + "✓" * 10))

    assert list(states) == ["0001"]
    assert states["0001"].mastered


def test_history_is_grouped_per_question(calculator: MasteryCalculator) -> None:
    history = _h("✗", number="0001") + _h("✓✓", number="0002")

    states = calculator.question_states(history)

    assert states["0001"].in_review
    assert states["0002"].mastered


def test_empty_history_yields_no_states_and_every_topic_insufficient(
    calculator: MasteryCalculator,
) -> None:
    totals = [TopicCount(topic="A", question_count=10), TopicCount(topic="B", question_count=4)]

    assert calculator.question_states([]) == {}
    result = calculator.topic_mastery({}, totals)

    assert {t.topic for t in result} == {"A", "B"}
    assert all(t.insufficient_data and t.seen == 0 for t in result)


def _topic_history(topic: str, mastered: int, in_review: int) -> list[AnsweredQuestion]:
    history: list[AnsweredQuestion] = []
    for i in range(mastered):
        history += _h("✓", number=f"{topic}-m{i}", topic=topic)
    for i in range(in_review):
        history += _h("✗", number=f"{topic}-r{i}", topic=topic)
    return history


def test_ranked_topics_ordered_by_mastery_ratio_then_insufficient_group(
    calculator: MasteryCalculator,
) -> None:
    history = (
        _topic_history("U", mastered=8, in_review=2)
        + _topic_history("T", mastered=4, in_review=6)
        + _topic_history("V", mastered=3, in_review=0)
    )
    totals = [
        TopicCount(topic="U", question_count=20),
        TopicCount(topic="T", question_count=20),
        TopicCount(topic="V", question_count=20),
    ]

    result = calculator.topic_mastery(calculator.question_states(history), totals)

    assert [t.topic for t in result] == ["T", "U", "V"]
    by_topic = {t.topic: t for t in result}
    assert (by_topic["T"].seen, by_topic["T"].mastered) == (10, 4)
    assert (by_topic["U"].seen, by_topic["U"].mastered) == (10, 8)
    assert not by_topic["T"].insufficient_data
    assert by_topic["V"].insufficient_data
    assert by_topic["V"].seen == 3


def test_insufficient_group_ordered_by_coverage_then_name(calculator: MasteryCalculator) -> None:
    history = _topic_history("B", mastered=2, in_review=0) + _topic_history(
        "C", mastered=1, in_review=0
    )
    totals = [
        TopicCount(topic="B", question_count=4),
        TopicCount(topic="C", question_count=10),
        TopicCount(topic="A", question_count=10),
        TopicCount(topic="Z", question_count=10),
    ]

    result = calculator.topic_mastery(calculator.question_states(history), totals)

    # A and Z unseen (0.0) by name, then C (0.1), then B (0.5).
    assert [t.topic for t in result] == ["A", "Z", "C", "B"]
    assert [t.seen for t in result] == [0, 0, 1, 2]


def test_seen_splits_into_mastered_and_in_review(calculator: MasteryCalculator) -> None:
    history = _topic_history("T", mastered=3, in_review=4)
    states = calculator.question_states(history)

    result = calculator.topic_mastery(states, [TopicCount(topic="T", question_count=9)])

    in_review = sum(1 for s in states.values() if s.in_review)
    assert result[0].seen == result[0].mastered + in_review
