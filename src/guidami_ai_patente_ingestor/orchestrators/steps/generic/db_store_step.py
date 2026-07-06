import logging
from typing import Any, cast

from flowstep import FlowContext, Step

from .protocols import StoreRepository

logger = logging.getLogger(__name__)


class DbStoreStep(Step):
    """Sink terminale: full-reload del repository (truncate + bulk_insert)."""

    def __init__(self, name: str, items_key: str, store_repo: StoreRepository) -> None:
        """Inietta la chiave context degli item e il repository (contratto StoreRepository)."""
        super().__init__(name)
        self._store_repo = store_repo
        self._items_key = items_key

    def execute(self, context: FlowContext) -> None:
        """Svuota la tabella e reinserisce in bulk gli item presenti in `items_key`."""
        items = cast(list[Any], context.get(self._items_key))
        self._store_repo.truncate()
        self._store_repo.bulk_insert(items)

    def get_required_keys(self) -> set[str]:
        """Ritorna `{items_key}`: lo step richiede gli item nel context."""
        return {self._items_key}

    def get_produced_keys(self) -> set[str]:
        """Ritorna `set()`: sink terminale, non produce nuove chiavi."""
        return set()
