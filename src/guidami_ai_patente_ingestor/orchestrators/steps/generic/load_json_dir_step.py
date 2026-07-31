"""Generic step that loads every element of a per-element layer directory.

Domain-agnostic: parametrized by model type and context key.
"""

import logging

from flowstep import FlowContext, Step

from commons.repositories import FileRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadJsonDirStep[T](Step):
    """Loads every element of a per-element layer directory into the context.

    Args:
        name:           Unique step name within the flow.
        input_layer:    Name of the input layer (e.g. ``"cleaned"``, ``"enriched"``).
        source:         Source key to load (e.g. ``"cds"``, ``"cap"``).
        output_key:     ``FlowContext`` key to write the list to.
        layer_resolver: Resolver mapping (layer, source) → container directory.
        repository:     Injected repository, already mapped onto the model to load.
    """

    def __init__(
        self,
        name: str,
        input_layer: str,
        source: str,
        output_key: str,
        layer_resolver: LayerResolver,
        repository: FileRepository[T],
    ) -> None:
        """Injects layer/source/context key, then resolver and repository."""
        super().__init__(name)
        self._input_layer = input_layer
        self._source = source
        self._output_key = output_key
        self._layer_resolver = layer_resolver
        self._repository = repository

    def execute(self, context: FlowContext) -> None:
        """Resolves the directory, loads every element, and writes the list to the context."""
        directory = self._layer_resolver.dir(self._input_layer, self._source)
        items = self._repository.load_all(directory)
        logger.info("Loaded %d items from '%s'", len(items), directory)
        context.put(self._output_key, items)

    def get_required_keys(self) -> set[str]:
        """No required key: this step is the flow's starting point."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produces the configured ``output_key``."""
        return {self._output_key}
