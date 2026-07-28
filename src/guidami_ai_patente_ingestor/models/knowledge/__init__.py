"""Intermediate models for the corpus normativo."""

from .cleaned_article import CleanedArticleModel
from .embeddable_chunk import EmbeddableChunkModel
from .enriched_article import EnrichedArticleModel
from .parsed_article import ParsedArticleModel

__all__ = [
    "CleanedArticleModel",
    "EmbeddableChunkModel",
    "EnrichedArticleModel",
    "ParsedArticleModel",
]
