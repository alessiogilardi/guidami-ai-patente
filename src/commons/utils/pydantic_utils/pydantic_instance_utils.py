"""Utilities for grouping Pydantic models by attributes."""

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel

from commons.utils.hash_utils import HashUtils

from .pydantic_model_utils import PydanticModelUtils

logger = logging.getLogger(__name__)


class PydanticInstanceUtils:
    """Utilities for grouping Pydantic models by attributes."""

    @classmethod
    def filter_by[T: BaseModel](
        cls,
        items: Sequence[T],
        validate: bool = True,
        **attributes: Any,
    ) -> list[T]:
        """Filter Pydantic models by attribute values."""
        if not attributes:
            raise ValueError("At least one attribute must be specified for filtering")

        if not items:
            return []

        if validate:
            # Validate against the attribute names (dict keys), not their values.
            PydanticModelUtils.validate_model_attributes(type(items[0]), *attributes.keys())

        return [item for item in items if cls._matches_attributes(item, attributes)]

    @classmethod
    def group_by[T: BaseModel](
        cls,
        items: Sequence[T],
        *attributes: str,
        validate: bool = True,
    ) -> dict[tuple[Any, ...], list[T]]:
        """Group Pydantic models by specified attributes."""
        if not attributes:
            raise ValueError("At least one attribute must be specified for grouping")

        if not items:
            return {}  # Empty dict, not an empty list, to match the declared return type.

        if validate:
            PydanticModelUtils.validate_model_attributes(type(items[0]), *attributes)

        groups = cls._create_groups(items, attributes)
        logger.info("Created %d groups out of %d original items", len(groups), len(items))
        return groups

    @classmethod
    def _matches_attributes(cls, item: BaseModel, attributes: dict[str, Any]) -> bool:
        """Check if an item matches all specified attribute values."""
        return all(getattr(item, key) == value for key, value in attributes.items())

    @classmethod
    def _create_groups[T: BaseModel](
        cls,
        items: Iterable[T],
        attributes: tuple[str, ...],
    ) -> dict[tuple[Any, ...], list[T]]:
        """Create groups from items based on attribute values."""
        groups: dict[tuple[Any, ...], list[T]] = defaultdict(list)

        for item in items:
            try:
                key = tuple(HashUtils.make_hashable(getattr(item, attr)) for attr in attributes)
                groups[key].append(item)
                logger.debug("Added to `%s` group (key) item: `%s`", key, item)
            except TypeError as e:
                raise TypeError(f"Error grouping item {item}: {str(e)}") from e

        # Return a plain dict to match the declared return type exactly.
        return dict(groups)
