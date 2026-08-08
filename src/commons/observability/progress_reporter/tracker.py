from collections.abc import Iterator, Sequence

from .protocols import ItemProgressReporter


def tracker[T](progress: ItemProgressReporter, label: str, items: Sequence[T]) -> Iterator[T]:
    """Iterates `items`, opening/closing a track on `progress` around them.

    Ticks one `advance_item()` after each item is consumed by the caller (i.e.
    right before the next one is yielded) — same timing as an explicit call at
    the end of a manual loop body.

    Args:
        progress: Reporter to open/close the item track on, and to advance.
        label: Short description of the items being tracked (e.g. "batches").
        items: Items to iterate; `len(items)` becomes the track's total.

    Yields:
        Each item from `items`, in order.
    """
    progress.begin_items(label, len(items))
    try:
        for item in items:
            yield item
            progress.advance_item()
    finally:
        progress.end_items()
