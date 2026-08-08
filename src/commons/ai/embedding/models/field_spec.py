from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

type Extractor = Callable[[Any], Any]
type Formatter = Callable[[Any], str]


def _extract_field(model: Any, attr_name: str) -> Any:
    """Reads `attr_name` from `model`, supporting both dicts and objects."""
    if isinstance(model, dict):
        return model.get(attr_name)
    return getattr(model, attr_name, None)


@dataclass(frozen=True)
class FieldSpec:
    """One field to extract and format when composing embedding text.

    dataclass, not BaseModel: `extractor`/`formatter` are `Callable` fields — Pydantic
    can't type a Callable field cleanly without `arbitrary_types_allowed=True`, which
    defeats the point of using Pydantic (code-conventions.md, Data structures).
    """

    extractor: Extractor
    label: str | None = None
    formatter: Formatter | None = None
    skip_if_none: bool = True

    @classmethod
    def from_attr(
        cls,
        attr_name: str,
        label: str | None = None,
        formatter: Formatter | None = None,
        skip_if_none: bool = True,
    ) -> "FieldSpec":
        """Factory extracting `attr_name` from a dict or object, no lambda needed."""
        return cls(
            extractor=lambda model: _extract_field(model, attr_name),
            label=label,
            formatter=formatter,
            skip_if_none=skip_if_none,
        )
