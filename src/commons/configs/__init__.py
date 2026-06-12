"""Configurazioni condivise tra ingestor e applicativo."""

from .embedding_config import EmbeddingConfig
from .vector_store_config import VectorStoreConfig

__all__ = ["EmbeddingConfig", "VectorStoreConfig"]
