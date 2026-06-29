"""Service per il calcolo batch di embedding e relativi contratti."""

from .embedding_service import EmbeddingService
from .protocols import Embeddable, Embedded

__all__ = ["Embeddable", "Embedded", "EmbeddingService"]
