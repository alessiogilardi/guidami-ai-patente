import pytest
from pydantic import BaseModel

from commons.utils.pydantic_utils import PydanticInstanceUtils


class _Quiz(BaseModel):
    topic: str
    number: str
    correct_answer: bool


def test_group_by_single_attribute() -> None:
    items = [
        _Quiz(topic="segnali", number="1", correct_answer=True),
        _Quiz(topic="segnali", number="2", correct_answer=False),
        _Quiz(topic="precedenza", number="3", correct_answer=True),
    ]
    result = PydanticInstanceUtils.group_by(items, "topic")
    assert result == {
        ("segnali",): [items[0], items[1]],
        ("precedenza",): [items[2]],
    }


def test_group_by_multiple_attributes() -> None:
    items = [
        _Quiz(topic="segnali", number="1", correct_answer=True),
        _Quiz(topic="segnali", number="1", correct_answer=False),
    ]
    result = PydanticInstanceUtils.group_by(items, "topic", "number")
    assert result == {
        ("segnali", "1"): [items[0], items[1]],
    }


def test_group_by_empty_items_returns_empty_dict() -> None:
    assert PydanticInstanceUtils.group_by([], "topic") == {}


def test_group_by_raises_when_no_attributes_given() -> None:
    with pytest.raises(ValueError, match="At least one attribute"):
        PydanticInstanceUtils.group_by([_Quiz(topic="a", number="1", correct_answer=True)])


def test_group_by_raises_for_invalid_attribute() -> None:
    with pytest.raises(ValueError, match="Invalid attributes"):
        PydanticInstanceUtils.group_by(
            [_Quiz(topic="a", number="1", correct_answer=True)], "unknown"
        )


def test_group_by_skips_validation_when_disabled() -> None:
    items = [_Quiz(topic="a", number="1", correct_answer=True)]
    result = PydanticInstanceUtils.group_by(items, "topic", validate=False)
    assert result == {("a",): items}


def test_filter_by_single_attribute() -> None:
    items = [
        _Quiz(topic="segnali", number="1", correct_answer=True),
        _Quiz(topic="segnali", number="2", correct_answer=False),
    ]
    result = PydanticInstanceUtils.filter_by(items, correct_answer=True)
    assert result == [items[0]]


def test_filter_by_empty_items_returns_empty_list() -> None:
    assert PydanticInstanceUtils.filter_by([], correct_answer=True) == []


def test_filter_by_raises_when_no_attributes_given() -> None:
    with pytest.raises(ValueError, match="At least one attribute"):
        PydanticInstanceUtils.filter_by([_Quiz(topic="a", number="1", correct_answer=True)])


def test_filter_by_raises_for_invalid_attribute() -> None:
    with pytest.raises(ValueError, match="Invalid attributes"):
        PydanticInstanceUtils.filter_by(
            [_Quiz(topic="a", number="1", correct_answer=True)], unknown="x"
        )
