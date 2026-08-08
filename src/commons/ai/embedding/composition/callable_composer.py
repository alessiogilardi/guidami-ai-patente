from collections.abc import Callable


class CallableComposer[T]:
    """Composes embedding text via any `Callable[[T], str]` — e.g. a model's own property.

    Implements `TextComposer[T]` structurally. Useful when a domain model already
    exposes its own text-building logic (a computed property, an existing helper
    function) and no further composition is needed — avoids writing a throwaway
    one-method class per model type just to satisfy the `TextComposer[T]` protocol.
    """

    def __init__(self, compose_fn: Callable[[T], str]) -> None:
        """Injects the function used to build the text for each model."""
        self._compose_fn = compose_fn

    def compose(self, model: T) -> str:
        """Returns the text to embed for `model`, via the injected callable."""
        return self._compose_fn(model)
