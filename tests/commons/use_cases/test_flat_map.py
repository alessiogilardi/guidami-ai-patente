"""Tests for FlatMap (UseCase that applies fn to each element and concatenates the results)."""

from unittest.mock import Mock


def test_flat_map_concatenates_results_in_order() -> None:
    from commons.use_cases import FlatMap

    result = FlatMap(lambda x: [x, x * 10])([1, 2, 3])
    assert result == [1, 10, 2, 20, 3, 30]


def test_flat_map_empty_input_list_returns_empty_list() -> None:
    from commons.use_cases import FlatMap

    result = FlatMap(lambda x: [x])([])
    assert result == []


def test_flat_map_element_producing_empty_list_contributes_nothing() -> None:
    from commons.use_cases import FlatMap

    def fn(x: int) -> list[int]:
        return [] if x == 2 else [x]

    result = FlatMap(fn)([1, 2, 3])
    assert result == [1, 3]


def test_flat_map_accepts_non_list_iterable_from_fn() -> None:
    from commons.use_cases import FlatMap

    def fn(x: int):  # noqa: ANN202 - deliberately untyped generator for the test
        yield x
        yield x + 1

    result = FlatMap(fn)([1, 3])
    assert result == [1, 2, 3, 4]


def test_flat_map_delegates_to_fn_via_dunder_call_for_each_element() -> None:
    from commons.use_cases import FlatMap

    fn = Mock(side_effect=lambda x: [x])
    FlatMap(fn)([1, 2, 3])

    assert fn.call_count == 3
    fn.assert_any_call(1)
    fn.assert_any_call(2)
    fn.assert_any_call(3)


def test_flat_map_is_use_case_subclass() -> None:
    from commons.use_cases import FlatMap, UseCase

    fm = FlatMap(lambda x: [x])
    assert isinstance(fm, UseCase)
