"""Modelli intermedi per il quiz bank (non persistiti in DB)."""

from .embeddable_quiz_question import EmbeddableQuizQuestion
from .enriched_quiz_bank import EnrichedQuizMainQuestion, EnrichedQuizSubQuestion
from .image_description import ImageDescription

__all__ = [
    "EmbeddableQuizQuestion",
    "EnrichedQuizMainQuestion",
    "EnrichedQuizSubQuestion",
    "ImageDescription",
]
