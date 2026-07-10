"""Clients for external services (embedding, Postgres, file system)."""

from .embeddings import EmbeddingClient, LiteLLMEmbeddingClient, SentenceTransformerEmbeddingClient
from .file_system import (
    AsyncFileReaderInterface,
    AsyncFileWriterInterface,
    AsyncLocalFileSystemClient,
    BaseFileSystemClient,
    FileReaderInterface,
    FileWriterInterface,
    LocalFileSystemClient,
)
from .postgres_client import PostgresClient

__all__ = [
    "AsyncFileReaderInterface",
    "AsyncFileWriterInterface",
    "AsyncLocalFileSystemClient",
    "BaseFileSystemClient",
    "EmbeddingClient",
    "FileReaderInterface",
    "FileWriterInterface",
    "LiteLLMEmbeddingClient",
    "LocalFileSystemClient",
    "PostgresClient",
    "SentenceTransformerEmbeddingClient",
]
