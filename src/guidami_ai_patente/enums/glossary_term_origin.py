"""Who produced a cited glossary term's definition (FR-8)."""

from enum import StrEnum, auto


class GlossaryTermOrigin(StrEnum):
    """Provenance of a `CitedGlossaryTerm`'s definition (FR-6, FR-8).

    `VERBATIM_CORPUS`: extracted by the offline `build-glossary` pass (spec 0019),
    verbatim from the corpus (ADR 0038). `AGENT_GENERATED`: generated live by
    `GlossaryEnricherAgent` (spec 0021), grounded on a retrieved comma when one is
    relevant, otherwise from the model's own general knowledge (FR-3).
    """

    VERBATIM_CORPUS = auto()
    AGENT_GENERATED = auto()
