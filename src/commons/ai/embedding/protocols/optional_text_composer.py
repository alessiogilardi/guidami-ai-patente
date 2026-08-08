from typing import Protocol


class OptionalTextComposer[T](Protocol):
    """Port for composing embedding text from a model of type `T`, when text may be absent.

    A model may have no text at all for this representation (e.g. an optional
    per-variant field). Counterpart of TextComposer[T] for the "may be absent" case:
    TextComposer[T] is used by ModelEmbeddingService[T] in the 1:1 pipeline, which
    always needs a str (EmbeddingResult.text: str is not Optional) — widening it to
    `str | None` would force a needless None-check on every 1:1 caller. This protocol
    exists instead of widening TextComposer[T].
    """

    def compose_or_none(self, model: T) -> str | None:
        """Returns the text to embed for `model`, or None if there is nothing to embed."""
        ...
