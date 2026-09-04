"""Raised when a requested image filename is not referenced by any quiz question."""

from .guidami_api_error import GuidamiApiError


class QuizImageNotFoundError(GuidamiApiError):
    """The filename is not referenced by any `quiz_questions.image_filename`.

    Raised **before** any filesystem access (FR-12, AD-24), so it covers both an
    honest miss and a traversal attempt — the endpoint never learns, and never needs
    to learn, whether a file of that name exists on disk.
    """

    def __init__(self, filename: str) -> None:
        """Builds the error for an unreferenced or malformed filename."""
        super().__init__(f"No quiz image named '{filename}'.")
