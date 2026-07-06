"""Data-access layer dell'ingestor."""

from .db import KnowledgeChunkStoreRepository, QuizQuestionStoreRepository

__all__ = [
    "KnowledgeChunkStoreRepository",
    "QuizQuestionStoreRepository",
]
