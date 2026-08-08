from typing import Protocol


class TextComposer[T](Protocol):
    """Port for composing embedding text from a model of type `T`.

    Genuine cross-package port (DIP): `ModelEmbeddingService[T]` depends on this
    abstraction, never on a concrete composer implementation.
    """

    def compose(self, model: T) -> str:
        """Returns the text to embed for `model`."""
        ...
