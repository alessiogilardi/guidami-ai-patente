"""Data-access layer dell'ingestor."""

from .db import KnowledgeChunkStoreRepository, QuizQuestionStoreRepository
from .json import JsonRepository

__all__ = [
    "JsonRepository",
    "KnowledgeChunkStoreRepository",
    "QuizQuestionStoreRepository",
]
