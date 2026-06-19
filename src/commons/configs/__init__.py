"""Configurazioni condivise tra ingestor e applicativo."""

from .agent_config import AgentConfig
from .embedding_config import EmbeddingConfig
from .postgres_connection_config import PostgresConnectionConfig

__all__ = ["EmbeddingConfig", "PostgresConnectionConfig", "AgentConfig"]
