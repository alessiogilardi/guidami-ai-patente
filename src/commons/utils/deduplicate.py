from collections.abc import Callable, Hashable, Iterable, Iterator


def deduplicate[T](
    items: Iterable[T],
    key: Callable[[T], Hashable],
    on_duplicate: Callable[[T], None] | None = None,
) -> Iterator[T]:
    """Filtra un iterabile restituendo un generatore di elementi unici.

    Args:
        items: L'iterabile da deduplicare.
        key: Funzione per estrarre la chiave di unicità (es. una tupla).
        on_duplicate: Callback opzionale da eseguire sui duplicati scartati.
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
