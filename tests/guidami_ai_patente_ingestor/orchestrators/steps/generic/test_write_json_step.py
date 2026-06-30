"""Test per WriteJsonStep generico."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import WriteJsonStep
from guidami_ai_patente_ingestor.repositories.json import JsonRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/data.json")
    return resolver


def test_required_keys_contains_input_key() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep("write", resolver, "cleaned", "cds", dict, "my_items")
    assert step.get_required_keys() == {"my_items"}


def test_produced_keys_is_empty_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep("write", resolver, "cleaned", "cds", dict, "my_items")
    assert step.get_produced_keys() == set()


def test_execute_writes_items_to_resolved_path() -> None:
    items = [{"id": 1}, {"id": 2}]
    resolver = _make_layer_resolver()

    with patch.object(JsonRepository, "write") as mock_write:
        step = WriteJsonStep("write", resolver, "enriched", "cap", dict, "my_items")
        context = FlowContext({"my_items": items})
        step.execute(context)

        expected_path = Path("/fake/enriched/cap/data.json")
        resolver.path.assert_called_once_with("enriched", "cap")
        mock_write.assert_called_once_with(items, expected_path)


def test_execute_resolves_path_for_configured_layer_and_source() -> None:
    resolver = _make_layer_resolver()

    with patch.object(JsonRepository, "write"):
        step = WriteJsonStep("write", resolver, "parsed", "cds", dict, "my_items")
        step.execute(FlowContext({"my_items": []}))

    resolver.path.assert_called_once_with("parsed", "cds")


def test_step_name_is_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonStep("my_write_step", resolver, "cleaned", "cds", dict, "my_items")
    assert step._name == "my_write_step"
