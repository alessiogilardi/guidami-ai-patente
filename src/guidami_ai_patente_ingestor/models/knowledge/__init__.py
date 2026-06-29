"""Modelli intermedi per il corpus normativo."""

from .embeddable_chunk import EmbeddableChunkModel
from .enriched_article import EnrichedArticleModel
from .parsed_article import ParsedArticleModel

__all__ = ["EmbeddableChunkModel", "EnrichedArticleModel", "ParsedArticleModel"]
