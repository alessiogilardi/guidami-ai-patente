from collections.abc import Callable, Iterable

from commons.use_cases.use_case import UseCase


class FlatMap[T, U](UseCase[Iterable[T], list[U]]):
    """Applies a callable to every element of an iterable and concatenates the results.

    Args:
        fn: Callable applied to each element; accepts `UseCase` instances
            (invoked via `__call__`) or any callable `T → Iterable[U]`.
    """

    def __init__(self, fn: Callable[[T], Iterable[U]]) -> None:
        """Injects the callable to apply to each element.

        Args:
            fn: Function or instantiated UseCase that produces, for each element,
                an `Iterable[U]` to concatenate into the final output.
        """
        self._fn = fn

    def execute(self, request: Iterable[T]) -> list[U]:
        """Applies `fn` to each element of `request` and concatenates the results.

        Args:
            request: Input iterable.

        Returns:
            Flat list with `fn` results concatenated, order preserved.
        """
        return [result for item in request for result in self._fn(item)]
