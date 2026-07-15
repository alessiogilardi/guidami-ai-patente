"""Tests for AsyncApplyStep (async twin of flowstep's ApplyStep, owns the event loop)."""

import asyncio
from collections.abc import Iterable
from typing import Any

from flowstep import FlowContext

from guidami_ai_patente_ingestor.orchestrators.steps.generic import AsyncApplyStep


def test_transforms_run_in_sequence() -> None:
    """Transform N+1 must start only after transform N has fully completed."""
    order: list[str] = []

    async def transform_one(items: Iterable[Any]) -> Iterable[Any]:
        order.append("t1-start")
        await asyncio.sleep(0)
        order.append("t1-end")
        return items

    async def transform_two(items: Iterable[Any]) -> Iterable[Any]:
        order.append("t2-start")
        await asyncio.sleep(0)
        order.append("t2-end")
        return items

    step = AsyncApplyStep(
        "sequence",
        transform_one,
        transform_two,
        input_key="input",
        output_key="output",
    )
    context = FlowContext({"input": [1, 2, 3]})

    step.execute(context)

    assert order == ["t1-start", "t1-end", "t2-start", "t2-end"]


def test_second_transform_receives_first_output() -> None:
    """The output of transform 1 must be threaded as the input of transform 2."""

    async def times_ten(items: Iterable[Any]) -> Iterable[Any]:
        return [x * 10 for x in items]

    async def plus_one(items: Iterable[Any]) -> Iterable[Any]:
        return [x + 1 for x in items]

    step = AsyncApplyStep(
        "threading",
        times_ten,
        plus_one,
        input_key="input",
        output_key="output",
    )
    context = FlowContext({"input": [1, 2, 3]})

    step.execute(context)

    assert context.get("output") == [11, 21, 31]


def test_writes_output_key_and_requires_input_key() -> None:
    async def identity(items: Iterable[Any]) -> Iterable[Any]:
        return items

    step = AsyncApplyStep(
        "identity",
        identity,
        input_key="my_input",
        output_key="my_output",
    )
    context = FlowContext({"my_input": [1, 2, 3]})

    step.execute(context)

    assert context.get("my_output") == [1, 2, 3]
    assert step.get_required_keys() == {"my_input"}
    assert step.get_produced_keys() == {"my_output"}


def test_execute_returns_none_and_owns_its_loop() -> None:
    """execute() is a plain sync call (no active loop in the test) and returns None.

    Proves it owns its own asyncio.run rather than expecting a running loop.
    """

    async def identity(items: Iterable[Any]) -> Iterable[Any]:
        return items

    step = AsyncApplyStep(
        "owns_loop",
        identity,
        input_key="input",
        output_key="output",
    )
    context = FlowContext({"input": [1]})

    result = step.execute(context)

    assert result is None
