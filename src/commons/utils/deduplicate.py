from collections.abc import Callable, Hashable, Iterable, Iterator


def deduplicate[T](
    items: Iterable[T],
    key: Callable[[T], Hashable],
    on_duplicate: Callable[[T], None] | None = None,
) -> Iterator[T]:
    """Filters an iterable, returning a generator of unique elements.

    Args:
        items: The iterable to deduplicate.
        key: Function to extract the uniqueness key (e.g. a tuple).
        on_duplicate: Optional callback executed on discarded duplicates.
    """
    seen: set[Hashable] = set()

    for item in items:
        k = key(item)
        if k in seen:
            if on_duplicate:
                on_duplicate(item)
            continue

        seen.add(k)
        yield item
