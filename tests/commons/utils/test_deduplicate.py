from collections.abc import Iterator

from commons.utils import deduplicate


def test_deduplicate_returns_unique_items() -> None:
    result = list(deduplicate([1, 2, 1, 3, 2], key=lambda x: x))
    assert result == [1, 2, 3]


def test_deduplicate_preserves_first_occurrence_order() -> None:
    result = list(deduplicate([3, 1, 2, 1, 3], key=lambda x: x))
    assert result == [3, 1, 2]


def test_deduplicate_empty_iterable_returns_empty() -> None:
    result = list(deduplicate([], key=lambda x: x))
    assert result == []


def test_deduplicate_all_unique_returns_all() -> None:
    result = list(deduplicate([1, 2, 3], key=lambda x: x))
    assert result == [1, 2, 3]


def test_deduplicate_calls_on_duplicate_for_each_duplicate() -> None:
    seen_dups: list[int] = []
    list(deduplicate([1, 2, 1, 3, 2], key=lambda x: x, on_duplicate=seen_dups.append))
    assert seen_dups == [1, 2]


def test_deduplicate_on_duplicate_none_does_not_raise() -> None:
    result = list(deduplicate([1, 1], key=lambda x: x, on_duplicate=None))
    assert result == [1]


def test_deduplicate_tuple_key() -> None:
    items = [("a", 1), ("b", 2), ("a", 1), ("a", 2)]
    result = list(deduplicate(items, key=lambda x: x))
    assert result == [("a", 1), ("b", 2), ("a", 2)]


def test_deduplicate_returns_iterator_not_list() -> None:
    result = deduplicate([1, 2], key=lambda x: x)
    assert isinstance(result, Iterator)


def test_deduplicate_works_with_generator_input() -> None:
    gen = (x for x in [1, 2, 1])
    result = list(deduplicate(gen, key=lambda x: x))
    assert result == [1, 2]
