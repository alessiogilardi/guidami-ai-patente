import pytest
from pydantic import BaseModel

from commons.utils.hash_utils import HashUtils


class _Item(BaseModel):
    name: str
    tags: list[str]


class _Unhashable:
    __hash__ = None  # type: ignore[assignment]


def test_make_hashable_passes_through_scalars() -> None:
    assert HashUtils.make_hashable(None) is None
    assert HashUtils.make_hashable("a") == "a"
    assert HashUtils.make_hashable(1) == 1
    assert HashUtils.make_hashable(1.5) == 1.5
    assert HashUtils.make_hashable(True) is True
    assert HashUtils.make_hashable(b"x") == b"x"


def test_make_hashable_converts_list_to_tuple() -> None:
    assert HashUtils.make_hashable([1, 2, 3]) == (1, 2, 3)


def test_make_hashable_converts_tuple_to_tuple() -> None:
    assert HashUtils.make_hashable((1, 2)) == (1, 2)


def test_make_hashable_converts_nested_list() -> None:
    assert HashUtils.make_hashable([[1, 2], [3]]) == ((1, 2), (3,))


def test_make_hashable_converts_dict_to_sorted_tuple() -> None:
    assert HashUtils.make_hashable({"b": 2, "a": 1}) == (("a", 1), ("b", 2))


def test_make_hashable_converts_set_to_frozenset() -> None:
    assert HashUtils.make_hashable({1, 2}) == frozenset({1, 2})


def test_make_hashable_converts_pydantic_model_via_dump() -> None:
    result = HashUtils.make_hashable(_Item(name="stop", tags=["a", "b"]))
    assert result == (("name", "stop"), ("tags", ("a", "b")))


def test_make_hashable_raises_type_error_for_unhashable_value() -> None:
    with pytest.raises(TypeError, match="not hashable"):
        HashUtils.make_hashable(_Unhashable())
