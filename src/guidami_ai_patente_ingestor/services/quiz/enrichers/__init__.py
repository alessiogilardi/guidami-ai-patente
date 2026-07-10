"""Quiz bank enrichers (Open/Closed: new enricher = new class)."""

from .image_description_enricher import ImageDescriptionEnricher
from .norm_reference_enricher import NormReferenceEnricher

__all__ = ["ImageDescriptionEnricher", "NormReferenceEnricher"]
