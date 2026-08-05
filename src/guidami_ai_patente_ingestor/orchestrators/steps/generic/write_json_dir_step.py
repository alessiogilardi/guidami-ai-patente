"""Generic step that writes one file per element into a layer directory.

Domain-agnostic: parametrized by model type, context key, and an `id_of` keyer.
"""

import logging
from collections.abc import Callable
from typing import cast

from flowstep import FlowContext, Step

from commons.repositories import FileRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class WriteJsonDirStep[T](Step):
    """Writes one JSON file per element into a per-element layer directory.

    Args:
        name:           Unique step name within the flow.
        output_layer:   Name of the output layer (e.g. ``"cleaned"``, ``"enriched"``).
        source:         Source key to write (e.g. ``"cds"``, ``"cap"``).
        input_key:      ``FlowContext`` key to read the list from.
        id_of:          Keyer deriving the stable filename stem for an element.
        layer_resolver: Resolver mapping (layer, source) → container directory.
        repository:     Injected repository, already mapped onto the model to write.
    """

    def __init__(
        self,
        name: str,
        output_layer: str,
        source: str,
        input_key: str,
        id_of: Callable[[T], str],
        layer_resolver: LayerResolver,
        repository: FileRepository[T],
    ) -> None:
        """Injects layer/source/key, then the keyer, resolver, and repository."""
        super().__init__(name)
        self._output_layer = output_layer
        self._source = source
        self._input_key = input_key
        self._id_of = id_of
        self._layer_resolver = layer_resolver
        self._repository = repository

    def execute(self, context: FlowContext) -> None:
        """Writes every element to its own file, named after `id_of`."""
        items = cast(list[T], context.get(self._input_key))
        directory = self._layer_resolver.dir(self._output_layer, self._source)

        for item in items:
            file_path = directory / f"{self._id_of(item)}.json"
            logger.debug("Writing element to '%s'", file_path)
            self._repository.write_one(item, file_path)

        logger.info("Wrote %d files to '%s'", len(items), directory)

    def get_required_keys(self) -> set[str]:
        """Requires ``input_key`` in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this step is the flow's endpoint."""
        return set()
