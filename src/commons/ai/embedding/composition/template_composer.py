import dataclasses
from collections.abc import Mapping
from string import Template
from typing import Any

from pydantic import BaseModel


class TemplateComposer[T]:
    """Composes embedding text via a `$var`-style `string.Template`.

    Implements `TextComposer[T]` structurally. Generic on `T` only at the
    `compose`/`_to_vars` boundary — see rationale in `protocols/text_composer.py`.

    Deliberately uses strict `.substitute()`, not `.safe_substitute()`
    (unlike `commons/ai/agents/utils/prompt_renderer.py::PromptRenderer`, which
    tolerates a partially-substituted LLM prompt): an unresolved placeholder here
    would end up embedded literally in the embedding text (e.g.
    "...$missing_field..."), a silent data-quality defect rather than an
    acceptable degraded output.
    """

    def __init__(self, template_str: str) -> None:
        r"""Injects the `$var`-style template, e.g. "Titolo: $title\nTesto: $body"."""
        self._template = Template(template_str)

    def compose(self, model: T) -> str:
        """Substitutes `model`'s fields into the template.

        Raises:
            KeyError: a `$placeholder` in the template has no matching field. Strict
                `substitute`, not `safe_substitute` — see class docstring above.
            TypeError: `model` is not a `BaseModel`, a dataclass instance, or a `Mapping`.
        """
        return self._template.substitute(**self._to_vars(model))

    @staticmethod
    def _to_vars(model: T) -> Mapping[str, Any]:
        """Dispatches `model` to a mapping of template substitution variables."""
        if isinstance(model, BaseModel):
            return model.model_dump()
        if dataclasses.is_dataclass(model) and not isinstance(model, type):
            return dataclasses.asdict(model)
        if isinstance(model, Mapping):
            return model
        raise TypeError(f"Unsupported model type for TemplateComposer: {type(model)!r}")
