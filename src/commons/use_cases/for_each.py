from collections.abc import Callable, Iterable

from commons.use_cases.use_case import UseCase


class ForEach[T, U](UseCase[Iterable[T], list[U]]):
    """Applies a callable to every element of an iterable.

    Args:
        fn: Callable applied to each element; accepts `UseCase` instances
            (invoked via `__call__`) or any callable `T → U`.
    """

    def __init__(self, fn: Callable[[T], U]) -> None:
        """Injects the callable to apply to each element.

        Args:
            fn: Function or instantiated UseCase to apply element by element.
        """
        self._fn = fn

    def execute(self, request: Iterable[T]) -> list[U]:
        """Applies `fn` to each element of `request`.

        Args:
            request: Input iterable.

        Returns:
            Transformed list in the same order.
        """
        return [self._fn(item) for item in request]
