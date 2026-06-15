"""Data-access layer dell'ingestor."""

from .article_repository import ArticleRepository
from .knowledge_chunk_store_repository import KnowledgeChunkStoreRepository
from .quiz_bank_repository import QuizBankRepository
from .quiz_question_store_repository import QuizQuestionStoreRepository

__all__ = [
    "ArticleRepository",
    "KnowledgeChunkStoreRepository",
    "QuizBankRepository",
    "QuizQuestionStoreRepository",
]
