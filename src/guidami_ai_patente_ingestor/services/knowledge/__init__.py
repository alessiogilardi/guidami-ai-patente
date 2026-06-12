"""Servizi per la trasformazione del corpus normativo in chunk indicizzabili."""

from .article_chunker import ArticleChunker
from .article_loader import ArticleLoader

__all__ = ["ArticleChunker", "ArticleLoader"]
