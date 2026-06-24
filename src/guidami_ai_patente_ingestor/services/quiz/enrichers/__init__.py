"""Enricher del quiz bank (Open/Closed: nuovo enricher = nuova classe)."""

from .image_description_enricher import ImageDescriptionEnricher
from .quiz_enricher import QuizEnricher

__all__ = ["ImageDescriptionEnricher", "QuizEnricher"]
