"""Test per LoadJsonStep generico."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import LoadJsonStep
from guidami_ai_patente_ingestor.repositories.json import JsonRepository
from guidami_ai_patente_ingestor.services import LayerResolver


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.path.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}/data.json")
    return resolver


def test_required_keys_is_empty_set() -> None:
    """Lo step è il punto di partenza del flow: nessuna chiave richiesta."""
    resolver = _make_layer_resolver()
    step = LoadJsonStep("load", resolver, "parsed", "cds", dict, "my_key")
    assert step.get_required_keys() == set()


def test_produced_keys_contains_output_key() -> None:
    resolver = _make_layer_resolver()
    step = LoadJsonStep("load", resolver, "enriched", "cap", dict, "my_key")
    assert step.get_produced_keys() == {"my_key"}


def test_execute_loads_source_and_puts_list_under_output_key() -> None:
    """Le items caricate dal repository finiscono nel context sotto output_key."""
    items = [{"a": 1}, {"b": 2}]
    resolver = _make_layer_resolver()

    with patch.object(JsonRepository, "load", return_value=items) as mock_load:
        step = LoadJsonStep("load", resolver, "parsed", "cds", dict, "my_key")
        context = FlowContext()
        step.execute(context)

        result = context.get("my_key")
        assert result is items

    mock_load.assert_called_once_with(Path("/fake/parsed/cds/data.json"))


def test_execute_resolves_path_with_configured_layer_and_source() -> None:
    """Il path risolto combina il layer e la source iniettati."""
    resolver = _make_layer_resolver()

    with patch.object(JsonRepository, "load", return_value=[]):
        step = LoadJsonStep("load", resolver, "enriched", "cap", dict, "my_key")
        step.execute(FlowContext())

    resolver.path.assert_called_once_with("enriched", "cap")


def test_step_name_is_set() -> None:
    """Regressione: il nome passato a __init__ deve essere esposto tramite Step._name."""
    resolver = _make_layer_resolver()
    step = LoadJsonStep("my_step_name", resolver, "parsed", "cds", dict, "my_key")
    assert step._name == "my_step_name"
