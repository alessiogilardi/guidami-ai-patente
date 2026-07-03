"""Enricher del quiz bank (Open/Closed: nuovo enricher = nuova classe)."""

from .image_description_enricher import ImageDescriptionEnricher
from .norm_reference_enricher import NormReferenceEnricher

__all__ = ["ImageDescriptionEnricher", "NormReferenceEnricher"]
