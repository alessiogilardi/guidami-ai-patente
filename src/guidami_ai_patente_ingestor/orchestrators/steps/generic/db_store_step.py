import logging
from typing import Any, cast

from flowstep import FlowContext, Step

from .protocols import StoreRepository

logger = logging.getLogger(__name__)


class DbStoreStep(Step):
    """Terminal sink: full-reload of the repository (truncate + bulk_insert)."""

    def __init__(self, name: str, items_key: str, store_repo: StoreRepository) -> None:
        """Injects the items context key and the repository (StoreRepository contract)."""
        super().__init__(name)
        self._store_repo = store_repo
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Empties the table and bulk-reinserts the items present in `items_key`."""
        items = cast(list[Any], context.get(self._items_key))
        self._store_repo.truncate()
        self._store_repo.bulk_insert(items)

    def get_required_keys(self) -> set[str]:
        """Returns `{items_key}`: the step requires the items in the context."""
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        """Returns `set()`: terminal sink, produces no new keys."""
        return set()
