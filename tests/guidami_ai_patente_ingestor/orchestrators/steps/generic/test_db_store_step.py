"""Test per DbStoreStep (sink terminale full-reload)."""

from typing import Any

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import DbStoreStep


class _RecordingRepo:
    """Soddisfa il Protocol StoreRepository. Registra le chiamate."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.inserted: list[Any] | None = None

    def truncate(self) -> None:
        self.events.append("truncate")

    def bulk_insert(self, items: list[Any], /) -> None:
        self.events.append("bulk_insert")
        self.inserted = items


def test_required_keys_and_produced_keys() -> None:
    repo = _RecordingRepo()
    step = DbStoreStep("store", store_repo=repo, items_key="my_items")
    assert step.get_required_keys() == {"my_items"}
    assert step.get_produced_keys() == set()


def test_execute_truncates_then_bulk_inserts_in_order() -> None:
    repo = _RecordingRepo()
    items = [{"id": 1}, {"id": 2}]
    context = FlowContext({"my_items": items})
    step = DbStoreStep("store", store_repo=repo, items_key="my_items")

    step.execute(context)

    assert repo.events == ["truncate", "bulk_insert"]
    assert repo.inserted is items
