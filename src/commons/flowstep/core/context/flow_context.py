"""Container for data shared between pipeline steps."""

from typing import Any


class FlowContext:
    """Container for data shared between pipeline steps.

    Provides a type-safe interface for storing and retrieving data
    during pipeline execution.

    Example:
        >>> context = FlowContext({"user_id": 123})
        >>> context.put("username", "john_doe")
        >>> username = context.get("username")
        >>> has_email = context.has("email")
    """

    def __init__(self, initial_data: dict[str, Any] | None = None):
        """Initialize the context with optional data.

        Args:
            initial_data: Dictionary with initial data
        """
        self._data: dict[str, Any] = initial_data.copy() if initial_data else {}

    def put(self, key: str, value: Any) -> None:
        """Set a value in the context.

        Args:
            key: Key to set
            value: Value to store
        """
        self._data[key] = value

    def get(self, key: str) -> Any:
        """Retrieve a value from the context.

        Args:
            key: Key to retrieve

        Returns:
            The value associated with the key

        Raises:
            KeyError
        """
        if not self.has(key):
            raise KeyError(key)

        return self._data.get(key)

    def has(self, key: str) -> bool:
        """Check if a key exists in the context.

        Args:
            key: Key to check

        Returns:
            True if the key exists, False otherwise
        """
        return key in self._data

    def keys(self) -> set[str]:
        """Return all keys present in the context.

        Returns:
            Set of all keys
        """
        return set(self._data.keys())

    def to_dict(self) -> dict[str, Any]:
        """Return a copy of the internal dictionary.

        Returns:
            Copy of the data dictionary
        """
        return self._data.copy()

    def __repr__(self) -> str:
        return f"FlowContext(keys={list(self.keys())})"
