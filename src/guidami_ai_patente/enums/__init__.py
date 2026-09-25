"""Closed vocabularies of the API (spec 0012)."""

from .explanation_result import ExplanationResult
from .explanation_status import ExplanationStatus
from .glossary_term_origin import GlossaryTermOrigin
from .insufficient_knowledge_reason import InsufficientKnowledgeReason

__all__ = [
    "ExplanationResult",
    "ExplanationStatus",
    "GlossaryTermOrigin",
    "InsufficientKnowledgeReason",
]
