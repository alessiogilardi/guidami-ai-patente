"""Data-access layer dell'ingestor."""

from .db import KnowledgeChunkStoreRepository, QuizQuestionStoreRepository
from .json import (
    ArticleRepository,
    EnrichedArticleRepository,
    EnrichedQuizBankRepository,
    QuizBankRepository,
)

__all__ = [
    "ArticleRepository",
    "EnrichedArticleRepository",
    "EnrichedQuizBankRepository",
    "KnowledgeChunkStoreRepository",
    "QuizBankRepository",
    "QuizQuestionStoreRepository",
]
