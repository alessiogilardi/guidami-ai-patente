from dataclasses import dataclass

from .field_spec import FieldSpec


@dataclass(frozen=True)
class EmbeddingSpec:
    """Declarative recipe for composing embedding text from a model's fields.

    dataclass, not BaseModel: it's an in-code composition recipe assembled by the
    caller, never parsed from external input; it also nests `FieldSpec` (itself a
    dataclass for the Callable-field reason above), so a matching type keeps the
    pair consistent instead of mixing a BaseModel wrapper around a dataclass field.
    """

    fields: list[FieldSpec]
    separator: str = "\n\n"
    normalize_whitespace: bool = True
