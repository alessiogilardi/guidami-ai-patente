"""Configurations shared between ingestor and application."""

from .open_router_config import OpenRouterConfig
from .postgres_connection_config import PostgresConnectionConfig

__all__ = ["PostgresConnectionConfig", "OpenRouterConfig"]
