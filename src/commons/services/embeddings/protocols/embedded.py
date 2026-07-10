from typing import Protocol, runtime_checkable

from .embeddable import Embeddable


@runtime_checkable
class Embedded(Embeddable, Protocol):
    """Embeddable with a writable slot for the resulting vector."""

    embedding: list[float] | None
