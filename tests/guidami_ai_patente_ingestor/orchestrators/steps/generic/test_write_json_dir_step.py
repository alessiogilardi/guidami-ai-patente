"""Tests for the generic WriteJsonDirStep."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

from flowstep import FlowContext

from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.orchestrators.steps.generic import WriteJsonDirStep
from guidami_ai_patente_ingestor.services import LayerResolver


@dataclass
class _Item:
    key: str


def _id_of(item: _Item) -> str:
    return item.key


def _make_layer_resolver() -> LayerResolver:
    resolver = MagicMock(spec=LayerResolver)
    resolver.dir.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}")
    return resolver


def _make_repository() -> JsonRepository:
    return MagicMock(spec=JsonRepository)


def test_required_keys_contains_input_key() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonDirStep(
        "write", "enriched", "cds", "my_items", _id_of, resolver, _make_repository()
    )
    assert step.get_required_keys() == {"my_items"}


def test_produced_keys_is_empty_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonDirStep(
        "write", "enriched", "cds", "my_items", _id_of, resolver, _make_repository()
    )
    assert step.get_produced_keys() == set()


def test_writes_one_file_per_element() -> None:
    items = [_Item("1"), _Item("2"), _Item("3")]
    resolver = _make_layer_resolver()
    repository = _make_repository()

    step = WriteJsonDirStep("write", "enriched", "cds", "my_items", _id_of, resolver, repository)
    step.execute(FlowContext({"my_items": items}))

    assert repository.write_one.call_count == 3


def test_filenames_match_id_of() -> None:
    items = [_Item("abc"), _Item("def")]
    resolver = _make_layer_resolver()
    repository = _make_repository()

    step = WriteJsonDirStep("write", "enriched", "cds", "my_items", _id_of, resolver, repository)
    step.execute(FlowContext({"my_items": items}))

    written_paths = [call.args[1] for call in repository.write_one.call_args_list]
    assert Path("/fake/enriched/cds/abc.json") in written_paths
    assert Path("/fake/enriched/cds/def.json") in written_paths


def test_step_name_is_set() -> None:
    resolver = _make_layer_resolver()
    step = WriteJsonDirStep(
        "my_write_step", "enriched", "cds", "my_items", _id_of, resolver, _make_repository()
    )
    assert step._name == "my_write_step"
