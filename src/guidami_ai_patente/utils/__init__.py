"""Standalone, stateless functions of the API — no injected dependency.

Domain-specific logic is fine here (see `.claude/rules/utils-package-placement.md`).
"""

from .merge_glossary_candidates import merge_glossary_candidates
from .normalize_term_casing import normalize_term_casing

__all__ = ["merge_glossary_candidates", "normalize_term_casing"]
