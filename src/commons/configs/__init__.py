"""Configurazioni condivise tra ingestor e applicativo."""

from .embedding_config import EmbeddingConfig
from .postgres_connection_config import PostgresConnectionConfig

__all__ = ["EmbeddingConfig", "PostgresConnectionConfig"]
