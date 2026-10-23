"""QuizSession carries its mode and topic with backwards-compatible defaults (AD-7)."""

from guidami_ai_patente_bot.enums import SessionMode
from guidami_ai_patente_bot.models import QuizSession


def test_defaults_to_random_mode_without_topic() -> None:
    session = QuizSession(seed="s", index=0, current_question_number="0001")

    assert session.mode is SessionMode.RANDOM
    assert session.topic is None


def test_carries_explicit_mode_and_topic() -> None:
    session = QuizSession(
        seed="s", index=1, current_question_number="0002", mode=SessionMode.TOPIC, topic="x"
    )

    assert session.mode is SessionMode.TOPIC
    assert session.topic == "x"
