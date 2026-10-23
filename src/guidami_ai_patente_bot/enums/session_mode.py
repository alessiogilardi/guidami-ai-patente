"""The flavour of quiz session a chat is running (AD-7)."""

from enum import StrEnum, auto


class SessionMode(StrEnum):
    """How a chat's questions are chosen: seeded random, restricted to a topic, or review."""

    RANDOM = auto()
    TOPIC = auto()
    REVIEW = auto()
