"""Generic step that loads a list of models from disk via a FileRepository.

Domain-agnostic: parametrized by model type and context key.
"""

import logging

from flowstep import FlowContext, Step

from commons.repositories import FileRepository
from guidami_ai_patente_ingestor.providers import LayerResolverProvider

logger = logging.getLogger(__name__)


class LoadJsonStep[T](Step):
    """Loads a list of models from disk and exposes it in the context under a given key.

    Args:
        name:           Unique step name within the flow.
        input_layer:    Name of the input layer (e.g. ``"parsed"``, ``"cleaned"``).
        source:         Source key to load (e.g. ``"cds"``, ``"quiz"``).
        output_key:     ``FlowContext`` key to write the list to.
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        repository:     Injected repository, already mapped onto the model to load.
    """

    def __init__(
        self,
        name: str,
        input_layer: str,
        source: str,
        output_key: str,
        layer_resolver: LayerResolverProvider,
        repository: FileRepository[T],
    ) -> None:
        """Injects layer/source/context key, then resolver and repository."""
        super().__init__(name)
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._source = source
        self._repository = repository
        self._output_key = output_key

    def execute(self, context: FlowContext) -> None:
        """Resolves the path, loads the list, and writes it to the context."""
        path = self._layer_resolver.path(self._input_layer, self._source)
        items = self._repository.load_list(path)
        logger.info("Loaded %d items for source '%s' via LoadJsonStep", len(items), self._source)

        context.put(self._output_key, items)

    def get_required_keys(self) -> set[str]:
        """No required key: this step is the flow's starting point."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produces the configured ``output_key``."""
        return {self._output_key}
