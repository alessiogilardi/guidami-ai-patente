"""Tests for the generic LoadJsonStep."""

from pathlib import Path
from unittest.mock import MagicMock

from flowstep import FlowContext

from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.orchestrators.steps.generic import LoadJsonStep
from guidami_ai_patente_ingestor.providers import LayerResolverProvider


def _make_layer_resolver() -> LayerResolverProvider:
    resolver = MagicMock(spec=LayerResolverProvider)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/data.json")
    return resolver


def _make_repository() -> JsonRepository:
    return MagicMock(spec=JsonRepository)


def test_required_keys_is_empty_set() -> None:
    """The step is the flow's starting point: no key is required."""
    resolver = _make_layer_resolver()
    step = LoadJsonStep("load", "parsed", "cds", "my_key", resolver, _make_repository())
    assert step.get_required_keys() == set()


def test_produced_keys_contains_output_key() -> None:
    resolver = _make_layer_resolver()
    step = LoadJsonStep("load", "enriched", "cap", "my_key", resolver, _make_repository())
    assert step.get_produced_keys() == {"my_key"}


def test_execute_loads_source_and_puts_list_under_output_key() -> None:
    """Items loaded from the repository end up in the context under output_key."""
    items = [{"a": 1}, {"b": 2}]
    resolver = _make_layer_resolver()
    repository = _make_repository()
    repository.load_list.return_value = items

    step = LoadJsonStep("load", "parsed", "cds", "my_key", resolver, repository)
    context = FlowContext()
    step.execute(context)

    result = context.get("my_key")
    assert result is items
    repository.load_list.assert_called_once_with(Path("/fake/parsed/cds/data.json"))


def test_execute_resolves_path_with_configured_layer_and_source() -> None:
    """The resolved path combines the injected layer and source."""
    resolver = _make_layer_resolver()
    repository = _make_repository()
    repository.load_list.return_value = []

    step = LoadJsonStep("load", "enriched", "cap", "my_key", resolver, repository)
    step.execute(FlowContext())

    resolver.path.assert_called_once_with("enriched", "cap")


def test_step_name_is_set() -> None:
    """Regression: the name passed to __init__ must be exposed via Step._name."""
    resolver = _make_layer_resolver()
    step = LoadJsonStep("my_step_name", "parsed", "cds", "my_key", resolver, _make_repository())
    assert step._name == "my_step_name"
