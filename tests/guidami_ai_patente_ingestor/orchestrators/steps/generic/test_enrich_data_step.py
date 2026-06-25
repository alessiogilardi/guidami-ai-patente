"""Test per EnrichDataStep generico (list-in/list-out, catena di enricher)."""

from unittest.mock import MagicMock

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import EnrichDataStep
from guidami_ai_patente_ingestor.orchestrators.steps.generic.protocols.enricher_protocol import (
    EnricherProtocol,
)


def _make_enricher(fn) -> EnricherProtocol:
    enricher = MagicMock(spec=EnricherProtocol)
    enricher.enrich.side_effect = fn
    return enricher


def test_required_keys_contains_input_key() -> None:
    step = EnrichDataStep("enrich", [], input_key="in", output_key="out")
    assert step.get_required_keys() == {"in"}


def test_produced_keys_contains_output_key() -> None:
    step = EnrichDataStep("enrich", [], input_key="in", output_key="out")
    assert step.get_produced_keys() == {"out"}


def test_execute_with_empty_enricher_list_is_passthrough() -> None:
    """Nessun enricher: la lista nel contesto deve restare identica (passthrough)."""
    items = ["a", "b", "c"]
    context = FlowContext({"in": items})
    step = EnrichDataStep("enrich", [], input_key="in", output_key="out")
    step.execute(context)

    assert context.get("out") == items


def test_execute_applies_single_enricher_to_whole_list_at_once() -> None:
    """L'enricher deve ricevere la lista intera in un'unica chiamata, non item per item."""

    def upper_all(items: list[str]) -> list[str]:
        return [item.upper() for item in items]

    enricher = _make_enricher(upper_all)
    items = ["a", "b", "c"]
    context = FlowContext({"in": items})
    step = EnrichDataStep("enrich", [enricher], input_key="in", output_key="out")
    step.execute(context)

    enricher.enrich.assert_called_once_with(items)
    assert context.get("out") == ["A", "B", "C"]


def test_execute_applies_multiple_enrichers_in_order() -> None:
    """Più enricher devono essere applicati in sequenza, ognuno sull'intera lista."""

    def append_x(items: list[str]) -> list[str]:
        return [item + "x" for item in items]

    def append_y(items: list[str]) -> list[str]:
        return [item + "y" for item in items]

    first = _make_enricher(append_x)
    second = _make_enricher(append_y)

    items = ["a", "b"]
    context = FlowContext({"in": items})
    step = EnrichDataStep("enrich", [first, second], input_key="in", output_key="out")
    step.execute(context)

    first.enrich.assert_called_once_with(["a", "b"])
    second.enrich.assert_called_once_with(["ax", "bx"])
    assert context.get("out") == ["axy", "bxy"]


def test_enrich_method_applies_chain_and_returns_list() -> None:
    """`enrich()` deve avere firma list-in/list-out, non item-in/item-out."""

    def double_all(items: list[int]) -> list[int]:
        return [item * 2 for item in items]

    enricher = _make_enricher(double_all)
    step = EnrichDataStep("enrich", [enricher], input_key="in", output_key="out")

    result = step.enrich([1, 2, 3])

    assert result == [2, 4, 6]
