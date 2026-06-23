"""Modelli intermedi per il quiz bank (non persistiti in DB)."""

from .embeddable_quiz import EmbeddableQuizModel
from .enriched_quiz import EnrichedQuizItemModel, EnrichedQuizModel
from .image_description import ImageDescription
from .quiz_bank import QuizBankItemModel, QuizBankModel

__all__ = [
    "EmbeddableQuizModel",
    "EnrichedQuizItemModel",
    "EnrichedQuizModel",
    "ImageDescription",
    "QuizBankItemModel",
    "QuizBankModel",
]
