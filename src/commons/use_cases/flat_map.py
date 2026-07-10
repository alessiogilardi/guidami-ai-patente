from collections.abc import Callable, Iterable

from commons.use_cases.use_case import UseCase


class FlatMap[T, U](UseCase[Iterable[T], list[U]]):
    """Applica un callable a ogni elemento di un iterabile e concatena i risultati.

    Args:
        fn: Callable applicato a ogni elemento; accetta istanze `UseCase`
            (invocate via `__call__`) o qualsiasi callable `T → Iterable[U]`.
    """

    def __init__(self, fn: Callable[[T], Iterable[U]]) -> None:
        """Inietta il callable da applicare a ogni elemento.

        Args:
            fn: Funzione o UseCase istanziato che produce, per ogni elemento,
                un `Iterable[U]` da concatenare all'output finale.
        """
        self._fn = fn

    def execute(self, request: Iterable[T]) -> list[U]:
        """Applica `fn` a ogni elemento di `request` e concatena i risultati.

        Args:
            request: Iterabile di input.

        Returns:
            Lista piatta con i risultati di `fn` concatenati, ordine preservato.
        """
        return [result for item in request for result in self._fn(item)]
