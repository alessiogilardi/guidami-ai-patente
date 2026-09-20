"""Raised when a caller asks to translate into a language this API does not serve."""

from .guidami_api_error import GuidamiApiError


class UnsupportedLanguageError(GuidamiApiError):
    """The requested `lang` is not one of the languages `/explanations/translate` supports.

    A `400` (spec 0018, FR-2). Only "ru" is implemented today; the query parameter
    stays open for a future language without requiring a new endpoint.
    """

    def __init__(self, lang: str) -> None:
        """Builds the error for the unsupported `lang` value."""
        super().__init__(f"Language '{lang}' is not supported for translation.")
