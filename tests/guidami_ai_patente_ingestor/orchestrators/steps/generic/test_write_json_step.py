"""Tests for the generic WriteJsonStep."""

from pathlib import Path
from unittest.mock import MagicMock

from flowstep import FlowContext

from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.orchestrators.steps.generic import WriteJsonStep
from guidami_ai_patente_ingestor.providers import LayerResolverProvider


def _make_layer_resolver() -> LayerResolverProvider:
    resolver = MagicMock(spec=LayerResolverProvider)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/data.json")
    return resolver


def _make_repository() -> JsonRepository:
    return MagicMock(spec=JsonRepository)


def test_required_keys_contains_input_key() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep("write", "cleaned", "cds", "my_items", resolver, _make_repository())
    assert step.get_required_keys() == {"my_items"}


def test_produced_keys_is_empty_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep("write", "cleaned", "cds", "my_items", resolver, _make_repository())
    assert step.get_produced_keys() == set()


def test_execute_writes_items_to_resolved_path() -> None:
    items = [{"id": 1}, {"id": 2}]
    resolver = _make_layer_resolver()
    repository = _make_repository()

    step = WriteJsonStep("write", "enriched", "cap", "my_items", resolver, repository)
    context = FlowContext({"my_items": items})
    step.execute(context)

    expected_path = Path("/fake/enriched/cap/data.json")
    resolver.path.assert_called_once_with("enriched", "cap")
    repository.write_list.assert_called_once_with(items, expected_path)


def test_execute_resolves_path_for_configured_layer_and_source() -> None:
    resolver = _make_layer_resolver()
    repository = _make_repository()

    step = WriteJsonStep("write", "parsed", "cds", "my_items", resolver, repository)
    step.execute(FlowContext({"my_items": []}))

    resolver.path.assert_called_once_with("parsed", "cds")


def test_step_name_is_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep(
        "my_write_step", "cleaned", "cds", "my_items", resolver, _make_repository()
    )
    assert step._name == "my_write_step"
