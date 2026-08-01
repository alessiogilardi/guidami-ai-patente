"""Intermediate models for the corpus normativo."""

from .cleaned_article import CleanedArticleModel
from .embeddable_article_comma import EmbeddableArticleComma
from .parsed_article import ParsedArticleModel, ParsedComma

__all__ = [
    "CleanedArticleModel",
    "EmbeddableArticleComma",
    "ParsedArticleModel",
    "ParsedComma",
]
