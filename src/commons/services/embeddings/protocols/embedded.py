from typing import Protocol, runtime_checkable

from .embeddable import Embeddable


@runtime_checkable
class Embedded(Embeddable, Protocol):
    """Embeddable con il cassetto scrivibile per il vettore risultante."""

    embedding: list[float] | None
