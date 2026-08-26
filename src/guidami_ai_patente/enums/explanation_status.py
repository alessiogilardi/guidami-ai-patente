"""Cache state of a question's comma association, advertised by the check response."""

from enum import StrEnum, auto


class ExplanationStatus(StrEnum):
    """What the client can expect if it asks for an explanation (FR-4, AD-4).

    Names the **cache state of the association**, not a latency: FR-5 invokes the
    writer on every request, so even `CACHED` costs a live LLM call. The client's
    real choice is between a short wait (writer only), a long one (retrieval + judge
    + writer) and no affordance at all.
    """

    CACHED = auto()
    UNCACHED = auto()
    UNAVAILABLE = auto()
