from collections.abc import Callable

from commons.use_cases.use_case import UseCase


class ForEach[T, U](UseCase[list[T], list[U]]):
    """Applica un callable a ogni elemento di una lista.

    Args:
        fn: Callable applicato a ogni elemento; accetta istanze `UseCase`
            (invocate via `__call__`) o qualsiasi callable `T → U`.
    """

    def __init__(self, fn: Callable[[T], U]) -> None:
        """Inietta il callable da applicare a ogni elemento.

        Args:
            fn: Funzione o UseCase istanziato da applicare elemento per elemento.
        """
        self._fn = fn

    def execute(self, request: list[T]) -> list[U]:
        """Applica `fn` a ogni elemento di `request`.

        Args:
            request: Lista di input.

        Returns:
            Lista trasformata nello stesso ordine.
        """
        return [self._fn(item) for item in request]
