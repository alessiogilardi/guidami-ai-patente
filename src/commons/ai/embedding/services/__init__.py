"""Services for batch embedding computation and their related contracts."""

from .embedding_service import EmbeddingService
from .model_embedding_service import ModelEmbeddingService

__all__ = ["EmbeddingService", "ModelEmbeddingService"]
