"""Generic step that applies a chain of async transforms under a single event loop.

The async twin of flowstep's ``ApplyStep``: it reads a value from the context, awaits
each async transform in sequence, and writes the result back. It owns the single
``asyncio.run`` for the whole chain, so every awaited transform shares one event loop —
avoiding cross-loop reuse of any client (e.g. a shared ``httpx.AsyncClient``) held by the
transforms. Transforms run strictly in order: transform N+1 starts only after transform N
has fully completed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from flowstep import (
    DataVolumeObserver,
    FlowContext,
    LoggingDataVolumeObserver,
    Step,
    track_data_volume,
)

logger = logging.getLogger(__name__)


class AsyncApplyStep(Step):
    """Applies one or more async transforms (Iterable → Awaitable[Iterable]) in sequence.

    Args:
        name: Unique step name within the flow.
        *transforms: Async callables applied in order; each awaited to completion before
            the next starts.
        input_key: Context key to read the source value from.
        output_key: Context key to write the result to.
        data_volume_observer: Observer notified with consumed/produced element counts.
            Defaults to ``LoggingDataVolumeObserver()``.
    """

    def __init__(
        self,
        name: str,
        *transforms: Callable[[Iterable[Any]], Awaitable[Iterable[Any]]],
        input_key: str,
        output_key: str,
        data_volume_observer: DataVolumeObserver | None = None,
    ) -> None:
        """Injects name, async transform chain, input/output keys and data volume observer."""
        super().__init__(name)
        self._transforms = transforms
        self._input_key = input_key
        self._output_key = output_key
        self._data_volume_observer: DataVolumeObserver = (
            data_volume_observer or LoggingDataVolumeObserver()
        )

    def execute(self, context: FlowContext) -> None:
        """Reads input_key, awaits the transform chain under one loop, writes output_key."""
        with track_data_volume(
            self._data_volume_observer, self, context, self._input_key, self._output_key
        ):
            result: Iterable[Any] = context.get(self._input_key)
            logger.debug(
                "AsyncApplyStep %r: applying %d async transform(s)",
                self.name,
                len(self._transforms),
            )
            result = asyncio.run(self._apply_chain(result))
            context.put(self._output_key, result)

    async def _apply_chain(self, result: Iterable[Any]) -> Iterable[Any]:
        """Awaits each transform in sequence; transform N+1 starts only after N completes."""
        for transform in self._transforms:
            result = await transform(result)
        return result

    def get_required_keys(self) -> set[str]:
        """Requires input_key in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produces output_key in the context."""
        return {self._output_key}
