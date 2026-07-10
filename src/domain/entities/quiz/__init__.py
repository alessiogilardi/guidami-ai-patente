"""Entities related to the quiz bank in the `quiz_questions` table."""

from .quiz_metadata import QuizMetadata
from .quiz_question import QuizQuestion

__all__ = ["QuizMetadata", "QuizQuestion"]
