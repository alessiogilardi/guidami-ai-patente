"""Data-access layer of the ingestor."""

from .db import KnowledgeChunkStoreRepository, QuizQuestionStoreRepository

__all__ = [
    "KnowledgeChunkStoreRepository",
    "QuizQuestionStoreRepository",
]
