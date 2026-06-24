"""Test per MapStep generico (1:1 mapping)."""

from commons.flowstep import FlowContext
from guidami_ai_patente_ingestor.orchestrators.steps.generic import MapStep


def _upper(text: str) -> str:
    return text.upper()


def test_required_keys_contains_input_key() -> None:
    step = MapStep("map", mapper=_upper, input_key="in", output_key="out")
    assert step.get_required_keys() == {"in"}


def test_produced_keys_contains_output_key() -> None:
    step = MapStep("map", mapper=_upper, input_key="in", output_key="out")
    assert step.get_produced_keys() == {"out"}


def test_execute_applies_mapper_to_each_item() -> None:
    items = ["a", "b", "c"]
    context = FlowContext({"in": items})
    step = MapStep("map", mapper=_upper, input_key="in", output_key="out")
    step.execute(context)

    result: list[str] = context.get("out")
    assert result == ["A", "B", "C"]


def test_execute_preserves_order() -> None:
    items = ["x", "y", "z"]
    context = FlowContext({"in": items})
    step = MapStep("map", mapper=_upper, input_key="in", output_key="out")
    step.execute(context)

    result: list[str] = context.get("out")
    assert result == ["X", "Y", "Z"]


def test_execute_1_to_1_no_filtering() -> None:
    """Lo step non filtra né duplica: output len == input len."""
    items = ["one", "two"]
    context = FlowContext({"in": items})
    step = MapStep("map", mapper=_upper, input_key="in", output_key="out")
    step.execute(context)

    result: list[str] = context.get("out")
    assert len(result) == 2


def test_step_name_is_set() -> None:
    """Regressione: MapStep deve chiamare super().__init__(name) per esporre _name."""
    step = MapStep("my_custom_name", mapper=_upper, input_key="in", output_key="out")
    assert step._name == "my_custom_name"


def test_execute_with_stub_mapper() -> None:
    """Mapper stub (lambda) funziona correttamente."""

    def double(n: int) -> int:
        return n * 2

    items = [1, 2, 3]
    context = FlowContext({"numbers": items})
    step = MapStep("double", mapper=double, input_key="numbers", output_key="doubled")
    step.execute(context)

    result: list[int] = context.get("doubled")
    assert result == [2, 4, 6]


def test_mapper_is_not_called_on_empty_list() -> None:
    executed = False

    def mapper(x: str) -> str:
        nonlocal executed
        executed = True
        return x

    context = FlowContext({"in": []})
    step = MapStep("map", mapper=mapper, input_key="in", output_key="out")
    step.execute(context)

    assert not executed
    assert context.get("out") == []
