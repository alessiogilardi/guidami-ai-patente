from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EmbeddingResult[T]:
    """Links a source model to the text sent for embedding and its vector.

    dataclass, not BaseModel: `model: T` is fully generic/opaque (dict, Pydantic
    model, or any domain object) and is handed back exactly as received, never
    parsed here. The PEP 695 generic syntax (`class Foo[T]`) matches
    `UseCase[T_In, T_Out]`/`ForEach[T, U]` in `commons/use_cases/`, verified in
    the repo, rather than `Generic[T]`/`TypeVar`. Frozen: a pure output value,
    never mutated after construction.
    """

    model: T
    text: str
    embedding: list[float]

    metadata: dict[str, Any] = field(default_factory=dict)
