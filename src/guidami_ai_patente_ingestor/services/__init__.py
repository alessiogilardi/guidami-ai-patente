"""Servizi di dominio dell'ingestor."""

from .layer_resolver import LayerResolver
from .quiz import QuizEnrichmentService

__all__ = ["LayerResolver", "QuizEnrichmentService"]
