"""Why an explanation cannot be produced, in a closed machine-readable vocabulary."""

from enum import StrEnum, auto


class InsufficientKnowledgeReason(StrEnum):
    """The `reason` of an `insufficient_knowledge` explanation response (FR-7, AD-6).

    `NOT_INDEXED` is deliberately separate from the two corpus-gap values: it is a
    **pipeline** gap, fixed by re-running ingestion, whereas `NO_SUPPORTING_NORM` is a
    **corpus** gap that no re-run fixes. Collapsing them would hide pipeline
    regressions permanently.

    Declared here with the rest of the API's vocabulary; the explanation endpoint that
    returns it arrives in plan 3.
    """

    NO_SUPPORTING_NORM = auto()
    NO_SUPPORTING_NORM_CONFIRMED = auto()
    NOT_INDEXED = auto()
