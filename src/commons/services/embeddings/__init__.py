"""Service per il calcolo batch di embedding e relativi contratti."""

from .embeddable import Embeddable, Embedded
from .embedding_service import EmbeddingService

__all__ = ["Embeddable", "Embedded", "EmbeddingService"]
