"""Entities related to the quiz bank in the `quiz_questions` table."""

from .quiz_image import QuizImageEntity
from .quiz_question import QuizQuestionEntity
from .quiz_question_embedding import QuizQuestionEmbeddingEntity

__all__ = ["QuizImageEntity", "QuizQuestionEmbeddingEntity", "QuizQuestionEntity"]
