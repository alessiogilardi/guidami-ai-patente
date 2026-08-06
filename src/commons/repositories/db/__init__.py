"""Read-only Postgres repositories, scoped per entity (AD-7)."""

from .corpus_read_repository import CorpusReadRepository
from .quiz_read_repository import QuizReadRepository

__all__ = ["CorpusReadRepository", "QuizReadRepository"]
