"""Raised when no quiz question matches the caller's selector."""

from .guidami_api_error import GuidamiApiError


class QuestionNotFoundError(GuidamiApiError):
    """No `quiz_questions` row matches the requested number, or the index is past the end.

    Both cases are a `404` (FR-1, FR-2, FR-3): the client asked for a question that
    does not exist. AD-31 notes the ambiguity this leaves — a typo'd `topic` and a
    fully-walked sequence look alike — and answers it with the topics endpoint
    (FR-16) rather than by splitting the status code.
    """

    def __init__(self, number: str) -> None:
        """Builds the error for an explicitly named question."""
        super().__init__(f"No quiz question with number '{number}'.")

    @classmethod
    def at_index(cls, seed: str, index: int) -> "QuestionNotFoundError":
        """Builds the error for a proposal index past the end of the filtered bank.

        Bypasses `__init__` because the message is about a position in a permutation,
        not about a number the client named.
        """
        error = cls.__new__(cls)
        GuidamiApiError.__init__(
            error,
            f"No quiz question at index {index} for seed '{seed}' under the requested filter.",
        )
        return error
