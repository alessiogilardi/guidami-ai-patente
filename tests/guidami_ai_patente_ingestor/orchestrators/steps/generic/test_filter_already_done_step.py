"""Tests for the generic FilterAlreadyDoneStep."""

import logging
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from flowstep import FlowContext

from commons.clients.file_system import LocalFileSystemClient
from guidami_ai_patente_ingestor.orchestrators.steps.generic import FilterAlreadyDoneStep
from guidami_ai_patente_ingestor.providers import LayerResolverProvider


@dataclass
class _Item:
    key: str


def _id_of(item: _Item) -> str:
    return item.key


def _make_layer_resolver() -> LayerResolverProvider:
    resolver = MagicMock(spec=LayerResolverProvider)
    resolver.dir.side_effect = lambda layer, src: Path(f"/fake/{layer}/{src}")
    return resolver


def _make_file_system_client(existing_stems: list[str]) -> LocalFileSystemClient:
    client = MagicMock(spec=LocalFileSystemClient)
    client.list_files.return_value = [
        Path(f"/fake/enriched/cds/{stem}.json") for stem in existing_stems
    ]
    return client


def _make_step(
    items_key: str = "items_in",
    output_key: str = "items_out",
    force: bool = False,
    existing_stems: list[str] | None = None,
) -> tuple[FilterAlreadyDoneStep, LocalFileSystemClient]:
    file_system_client = _make_file_system_client(existing_stems or [])
    step = FilterAlreadyDoneStep(
        "filter",
        items_key,
        output_key,
        "enriched",
        "cds",
        force,
        _id_of,
        _make_layer_resolver(),
        file_system_client,
    )
    return step, file_system_client


def test_required_keys_contains_input_key() -> None:
    step, _ = _make_step(items_key="my_items")
    assert step.get_required_keys() == {"my_items"}


def test_produced_keys_contains_output_key() -> None:
    step, _ = _make_step(output_key="my_output")
    assert step.get_produced_keys() == {"my_output"}


def test_keeps_only_missing() -> None:
    items = [_Item("1"), _Item("2"), _Item("3")]
    step, _ = _make_step(existing_stems=["2"])

    context = FlowContext({"items_in": items})
    step.execute(context)

    kept = context.get("items_out")
    assert [item.key for item in kept] == ["1", "3"]


def test_force_passes_everything_even_if_already_present() -> None:
    items = [_Item("1"), _Item("2")]
    step, file_system_client = _make_step(force=True, existing_stems=["1", "2"])

    context = FlowContext({"items_in": items})
    step.execute(context)

    assert context.get("items_out") == items
    file_system_client.list_files.assert_not_called()


def test_empty_dest_keeps_all() -> None:
    items = [_Item("1"), _Item("2")]
    step, _ = _make_step(existing_stems=[])

    context = FlowContext({"items_in": items})
    step.execute(context)

    assert context.get("items_out") == items


def test_warns_when_nothing_left(caplog: pytest.LogCaptureFixture) -> None:
    items = [_Item("1"), _Item("2")]
    step, _ = _make_step(existing_stems=["1", "2"])

    with caplog.at_level(logging.WARNING):
        context = FlowContext({"items_in": items})
        step.execute(context)

    assert context.get("items_out") == []
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_step_name_is_set() -> None:
    file_system_client = _make_file_system_client([])
    step = FilterAlreadyDoneStep(
        "my_step_name",
        "items_in",
        "items_out",
        "enriched",
        "cds",
        False,
        _id_of,
        _make_layer_resolver(),
        file_system_client,
    )
    assert step._name == "my_step_name"
