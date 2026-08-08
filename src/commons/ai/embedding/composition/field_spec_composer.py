import re
from typing import Any

from commons.ai.embedding.models import EmbeddingSpec, FieldSpec


class FieldSpecComposer[T]:
    """Composes embedding text from a model using a declarative EmbeddingSpec.

    Implements both `TextComposer[T]` (`compose`, always a string — the 1:1 case) and
    `OptionalTextComposer[T]` (`compose_or_none`, `None` when a field marked
    `skip_if_none=False` is missing — the "may have nothing to embed" case), structurally,
    no explicit inheritance. Callers pick whichever method matches their pipeline's
    contract; both read the same `EmbeddingSpec`. Generic on `T` only at the compose
    boundary, to match the model type flowing through the injecting caller;
    `EmbeddingSpec` itself stays untyped (see rationale in `protocols/text_composer.py`).
    """

    def __init__(self, spec: EmbeddingSpec) -> None:
        """Injects the declarative composition recipe."""
        self._spec = spec

    def compose(self, model: T) -> str:
        """Extracts, formats, and joins the spec's fields into embedding text."""
        sections = [self._render(field, value) for field, value in self._extract(model)]
        text = self._spec.separator.join(sections)
        return self._normalize_whitespace(text) if self._spec.normalize_whitespace else text

    def compose_or_none(self, model: T) -> str | None:
        """Like `compose`, but returns None if a required field is missing.

        A field marked `skip_if_none=False` ("required") that extracts to None means
        there is nothing meaningful to embed for this model — signals that, instead of
        composing around the hole.
        """
        if self._missing_required_field(model):
            return None
        return self.compose(model)

    def _missing_required_field(self, model: T) -> bool:
        return any(
            field.extractor(model) is None for field in self._spec.fields if not field.skip_if_none
        )

    def _extract(self, model: T) -> list[tuple[FieldSpec, Any]]:
        """Extracts each field's raw value once, dropping unset fields that opt out."""
        pairs = [(field, field.extractor(model)) for field in self._spec.fields]
        return [pair for pair in pairs if self._is_set(*pair)]

    @staticmethod
    def _is_set(field: FieldSpec, value: Any) -> bool:
        """True unless `value` is missing and `field` opts out of missing values."""
        return value is not None or not field.skip_if_none

    @staticmethod
    def _render(field: FieldSpec, value: Any) -> str:
        """Formats one (field, value) pair into its `"label: value"` or bare `value` line."""
        if field.formatter:
            value = field.formatter(value)
        return f"{field.label}: {value}" if field.label else str(value)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapses 3+ consecutive newlines into a double newline and trims edges."""
        return re.sub(r"\n{3,}", "\n\n", text).strip()
