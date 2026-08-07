"""Data-access layer of the ingestor."""

from .db import (
    ArticleCommaStoreRepository,
    ArticleStoreRepository,
    QuizImageStoreRepository,
    QuizQuestionStoreRepository,
)

__all__ = [
    "ArticleCommaStoreRepository",
    "ArticleStoreRepository",
    "QuizImageStoreRepository",
    "QuizQuestionStoreRepository",
]
