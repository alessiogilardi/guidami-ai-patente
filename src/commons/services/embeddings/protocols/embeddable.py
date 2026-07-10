from typing import Protocol, runtime_checkable


@runtime_checkable
class Embeddable(Protocol):
    """Object exposing the text to embed (read-only)."""

    @property
    def embedded_text(self) -> str:
        """Text to use for computing the embedding."""
        ...
