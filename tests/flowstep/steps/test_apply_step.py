"""Test per ApplyStep (step generico che applica una catena di transform lista→lista)."""

from flowstep import FlowContext, Step


def test_single_transform_reads_input_applies_and_writes_output() -> None:
    from flowstep.steps import ApplyStep

    context = FlowContext({"items": [1, 2, 3]})

    def double(items: list[int]) -> list[int]:
        return [x * 2 for x in items]

    step = ApplyStep("double", double, input_key="items", output_key="result")
    step.execute(context)

    assert context.get("result") == [2, 4, 6]


def test_chain_of_two_transforms_applied_in_order() -> None:
    from flowstep.steps import ApplyStep

    context = FlowContext({"items": ["a", "b"]})

    def upper(items: list[str]) -> list[str]:
        return [s.upper() for s in items]

    def exclaim(items: list[str]) -> list[str]:
        return [s + "!" for s in items]

    step = ApplyStep("chain", upper, exclaim, input_key="items", output_key="result")
    step.execute(context)

    assert context.get("result") == ["A!", "B!"]


def test_empty_input_list_produces_empty_output() -> None:
    from flowstep.steps import ApplyStep

    context = FlowContext({"items": []})

    def double(items: list[int]) -> list[int]:
        return [x * 2 for x in items]

    step = ApplyStep("double", double, input_key="items", output_key="result")
    step.execute(context)

    assert context.get("result") == []


def test_get_required_keys_returns_input_key() -> None:
    from flowstep.steps import ApplyStep

    step = ApplyStep("s", lambda x: x, input_key="in", output_key="out")
    assert step.get_required_keys() == {"in"}


def test_get_produced_keys_returns_output_key() -> None:
    from flowstep.steps import ApplyStep

    step = ApplyStep("s", lambda x: x, input_key="in", output_key="out")
    assert step.get_produced_keys() == {"out"}


def test_apply_step_is_a_step_subclass() -> None:
    from flowstep.steps import ApplyStep

    step = ApplyStep("s", lambda x: x, input_key="in", output_key="out")
    assert isinstance(step, Step)


def test_no_transforms_passes_input_through_unchanged() -> None:
    from flowstep.steps import ApplyStep

    context = FlowContext({"items": [10, 20]})
    step = ApplyStep("passthrough", input_key="items", output_key="result")
    step.execute(context)

    assert context.get("result") == [10, 20]
