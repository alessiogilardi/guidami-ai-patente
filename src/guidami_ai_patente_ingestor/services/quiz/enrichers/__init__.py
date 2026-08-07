"""Quiz bank enrichers (Open/Closed: new enricher = new class)."""

from .image_description_enricher import ImageDescriptionEnricherService
from .norm_reference_enricher import NormReferenceEnricherService

__all__ = ["ImageDescriptionEnricherService", "NormReferenceEnricherService"]
