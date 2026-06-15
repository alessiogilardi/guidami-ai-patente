"""Servizi per la trasformazione del corpus normativo in chunk indicizzabili."""

from .article_chunker import ArticleChunker
from .article_cleaner import ArticleCleaner

__all__ = ["ArticleChunker", "ArticleCleaner"]
