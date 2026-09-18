"""Raised when a question has an embedding but no current comma labeling."""

from .guidami_api_error import GuidamiApiError


class LabelingNotReadyError(GuidamiApiError):
    """The caller asked for an explanation without ensuring it was labeled first.

    A `409` (spec 0017, AD-4): the question's embedding exists, so retrieval could
    run, but no current labeling has been written yet — `POST
    /quiz-questions/{number}/label` should have been called first. Distinct from
    `not_indexed` (no embedding at all, a permanent pipeline gap) and from
    `insufficient_knowledge` (the judge already ran and found nothing): this is a
    transient contract violation, not a statement about the corpus.
    """

    def __init__(self, number: str) -> None:
        """Records the unlabeled question `number`."""
        super().__init__(f"Question '{number}' is embedded but has no current labeling.")
