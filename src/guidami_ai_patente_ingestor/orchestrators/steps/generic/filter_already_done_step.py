"""Generic step that drops elements whose destination file already exists.

Domain-agnostic: parametrized by an `id_of` keyer supplied by the caller.
"""

import logging
from collections.abc import Callable
from typing import cast

from flowstep import FlowContext, Step

from commons.clients.file_system import LocalFileSystemClient
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class FilterAlreadyDoneStep[T](Step):
    """Drops the elements whose destination file already exists.

    Args:
        name:               Unique step name within the flow.
        input_key:          ``FlowContext`` key to read the list from.
        output_key:         ``FlowContext`` key to write the filtered list to.
        dest_layer:         Name of the destination layer (e.g. ``"enriched"``).
        source:             Source key (e.g. ``"cds"``, ``"cap"``).
        force:              If True, every element is kept (no filesystem check).
        id_of:              Keyer deriving the stable filename stem for an element.
        layer_resolver:     Resolver mapping (layer, source) → container directory.
        file_system_client: Client used to list the destination directory.
    """

    def __init__(
        self,
        name: str,
        input_key: str,
        output_key: str,
        dest_layer: str,
        source: str,
        force: bool,
        id_of: Callable[[T], str],
        layer_resolver: LayerResolver,
        file_system_client: LocalFileSystemClient,
    ) -> None:
        """Injects layer/source/keys/force, then the keyer, resolver, and client."""
        super().__init__(name)
        self._input_key = input_key
        self._output_key = output_key
        self._dest_layer = dest_layer
        self._source = source
        self._force = force
        self._id_of = id_of
        self._layer_resolver = layer_resolver
        self._file_system_client = file_system_client

    def execute(self, context: FlowContext) -> None:
        """Filters out elements whose destination file already exists.

        With `force`, every element is kept and no filesystem listing happens.
        Logs at `info` how many elements were kept; if none, escalates to a
        `warning` (Decision 11) since a silent no-op run is otherwise invisible.
        """
        items = cast(list[T], context.get(self._input_key))

        if self._force:
            logger.info("Force enabled: keeping all %d elements", len(items))
            context.put(self._output_key, items)
            return

        destination = self._layer_resolver.dir(self._dest_layer, self._source)
        already_done = {p.stem for p in self._file_system_client.list_files(destination)}
        kept = [item for item in items if self._id_of(item) not in already_done]

        if kept:
            logger.info(
                "Kept %d of %d elements (%d already present in '%s')",
                len(kept),
                len(items),
                len(items) - len(kept),
                self._dest_layer,
            )
        else:
            logger.warning(
                "Nothing to process: all %d elements already present in '%s'",
                len(items),
                self._dest_layer,
            )

        context.put(self._output_key, kept)

    def get_required_keys(self) -> set[str]:
        """Requires ``input_key`` in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produces the configured ``output_key``."""
        return {self._output_key}
