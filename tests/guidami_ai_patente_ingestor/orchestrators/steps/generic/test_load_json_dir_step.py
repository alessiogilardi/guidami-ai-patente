"""Tests for the generic LoadJsonDirStep."""

from pathlib import Path
from unittest.mock import MagicMock

from flowstep import FlowContext

from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.orchestrators.steps.generic import LoadJsonDirStep
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.dir.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}")
    return resolver


def _make_repository() -> JsonRepository:
    return MagicMock(spec=JsonRepository)


def test_required_keys_is_empty_set() -> None:
    """The step is the flow's starting point: no key is required."""
    resolver = _make_layer_resolver()
    step = LoadJsonDirStep("load", "cleaned", "cds", "my_key", resolver, _make_repository())
    assert step.get_required_keys() == set()


def test_produced_keys_contains_output_key() -> None:
    resolver = _make_layer_resolver()
    step = LoadJsonDirStep("load", "enriched", "cap", "my_key", resolver, _make_repository())
    assert step.get_produced_keys() == {"my_key"}


def test_execute_loads_all_items_and_puts_list_under_output_key() -> None:
    items = [{"a": 1}, {"b": 2}]
    resolver = _make_layer_resolver()
    repository = _make_repository()
    repository.load_all.return_value = items

    step = LoadJsonDirStep("load", "cleaned", "cds", "my_key", resolver, repository)
    context = FlowContext()
    step.execute(context)

    assert context.get("my_key") is items
    repository.load_all.assert_called_once_with(Path("/fake/cleaned/cds"))


def test_execute_resolves_dir_with_configured_layer_and_source() -> None:
    resolver = _make_layer_resolver()
    repository = _make_repository()
    repository.load_all.return_value = []

    step = LoadJsonDirStep("load", "enriched", "cap", "my_key", resolver, repository)
    step.execute(FlowContext())

    resolver.dir.assert_called_once_with("enriched", "cap")


def test_missing_dir_yields_empty_list() -> None:
    """A missing directory (repository.load_all returns []) does not fail the step."""
    resolver = _make_layer_resolver()
    repository = _make_repository()
    repository.load_all.return_value = []

    step = LoadJsonDirStep("load", "cleaned", "cds", "my_key", resolver, repository)
    context = FlowContext()
    step.execute(context)

    assert context.get("my_key") == []


def test_step_name_is_set() -> None:
    resolver = _make_layer_resolver()
    step = LoadJsonDirStep(
        "my_step_name", "cleaned", "cds", "my_key", resolver, _make_repository()
    )
    assert step._name == "my_step_name"
