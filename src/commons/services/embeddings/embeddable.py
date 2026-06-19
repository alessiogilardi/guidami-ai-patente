from typing import Protocol, runtime_checkable


@runtime_checkable
class Embeddable(Protocol):
    """Oggetto che espone il testo da embeddare (sola lettura)."""

    @property
    def embedded_text(self) -> str:
        """Testo da usare per il calcolo dell'embedding."""
        ...


@runtime_checkable
class Embedded(Embeddable, Protocol):
    """Embeddable con il cassetto scrivibile per il vettore risultante."""

    embedding: list[float] | None
