"""Entità di dominio dell'ingestor."""

from .article import Article
from .quiz_bank import QuizMainQuestion, QuizSubQuestion

__all__ = [
    "Article",
    "QuizMainQuestion",
    "QuizSubQuestion",
]
