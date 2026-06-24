"""Modelli intermedi per il quiz bank (non persistiti in DB)."""

from .cleaned_quiz import CleanedQuizModel
from .embeddable_quiz import EmbeddableQuizModel
from .enriched_quiz import EnrichedQuizModel
from .image_description import ImageDescription
from .parsed_quiz import ParsedQuizItemModel, ParsedQuizModel

__all__ = [
    "CleanedQuizModel",
    "EmbeddableQuizModel",
    "EnrichedQuizModel",
    "ImageDescription",
    "ParsedQuizItemModel",
    "ParsedQuizModel",
]
