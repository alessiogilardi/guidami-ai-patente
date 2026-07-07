"""Servizi di dominio per la preparazione e l'indexing del quiz bank."""

from .embed_quiz_metadata import EmbedQuizMetadata
from .enrichers import ImageDescriptionEnricher

__all__ = ["EmbedQuizMetadata", "ImageDescriptionEnricher"]
