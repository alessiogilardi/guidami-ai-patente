from typing import Any

from pydantic import BaseModel


class HashUtils:
    """Utilities for converting values into hashable representations."""

    @classmethod
    def make_hashable(cls, value: Any) -> Any:
        """Convert a value to a hashable type suitable for use as a dictionary key.

        Args:
            value: The value to convert

        Returns:
            A hashable representation of the value

        Raises:
            TypeError: If the value cannot be made hashable
        """
        if value is None or isinstance(value, (str, int, float, bool, bytes)):
            return value

        try:
            if isinstance(value, (list, tuple)):
                return tuple(cls.make_hashable(item) for item in value)

            if isinstance(value, dict):
                return tuple(sorted((k, cls.make_hashable(v)) for k, v in value.items()))

            if isinstance(value, set):
                return frozenset(cls.make_hashable(item) for item in value)

            if isinstance(value, BaseModel):
                return cls.make_hashable(value.model_dump())

            # Fallback
            hash(value)
            return value

        except TypeError as e:
            raise TypeError(
                f"Cannot group by attribute of type {type(value).__name__}: "
                f"not hashable or contains unhashable nested items. Value: {value}"
            ) from e
