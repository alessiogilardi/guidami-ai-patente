"""Test per ForEach (UseCase che mappa un callable su ogni elemento di una lista)."""


def test_for_each_applies_fn_to_each_item() -> None:
    from commons.use_cases import ForEach

    result = ForEach(lambda x: x * 2)([1, 2, 3])
    assert result == [2, 4, 6]


def test_for_each_empty_list_returns_empty_list() -> None:
    from commons.use_cases import ForEach

    result = ForEach(lambda x: x)([])
    assert result == []


def test_for_each_preserves_order() -> None:
    from commons.use_cases import ForEach

    result = ForEach(str)([3, 1, 2])
    assert result == ["3", "1", "2"]


def test_for_each_with_use_case_instance_as_fn() -> None:
    from commons.use_cases import ForEach, UseCase

    class Double(UseCase[int, int]):
        def execute(self, request: int) -> int:
            return request * 2

    double = Double()
    result = ForEach(double)([4, 5])
    assert result == [8, 10]


def test_for_each_is_use_case_subclass() -> None:
    from commons.use_cases import ForEach, UseCase

    fe = ForEach(lambda x: x)
    assert isinstance(fe, UseCase)


def test_for_each_is_callable_via_dunder_call() -> None:
    from commons.use_cases import ForEach

    fe = ForEach(lambda x: x + 1)
    result = fe([10, 20])
    assert result == [11, 21]
