"""Service for batch embedding computation and its related contracts."""

from .embedding_service import EmbeddingService
from .protocols import Embeddable, Embedded

__all__ = ["Embeddable", "Embedded", "EmbeddingService"]
