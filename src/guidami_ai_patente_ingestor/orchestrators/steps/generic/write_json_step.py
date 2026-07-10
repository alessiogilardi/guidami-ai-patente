"""Generic step that writes a list of models to disk via JsonRepository.

Domain-agnostic: parametrized by model type and context key.
"""

import logging
from typing import cast

from flowstep import FlowContext, Step

from commons.repositories import JsonRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class WriteJsonStep[T](Step):
    """Writes a list of models to disk for a given (layer, source).

    Args:
        name:           Unique step name within the flow.
        output_layer:   Name of the output layer (e.g. ``"cleaned"``, ``"enriched"``).
        source:         Source key to write (e.g. ``"cds"``, ``"quiz"``).
        input_key:      ``FlowContext`` key to read the list from.
        layer_resolver: Resolver mapping (layer, source) → JSON file Path.
        repository:     Injected repository, already mapped onto the model to write.
    """

    def __init__(
        self,
        name: str,
        output_layer: str,
        source: str,
        input_key: str,
        layer_resolver: LayerResolver,
        repository: JsonRepository[T],
    ) -> None:
        """Injects layer/source/context key, then resolver and repository."""
        super().__init__(name)
        self._layer_resolver = layer_resolver
        self._output_layer = output_layer
        self._source = source
        self._repository = repository
        self._input_key = input_key

    def execute(self, context: FlowContext) -> None:
        """Reads the list from the context and writes it to the resolved path."""
        items = cast(list[T], context.get(self._input_key))
        path = self._layer_resolver.path(self._output_layer, self._source)
        self._repository.write(items, path)

        logger.info(
            "WriteJsonStep: wrote %d items for source '%s'",
            len(items),
            self._source,
        )

    def get_required_keys(self) -> set[str]:
        """Requires ``input_key`` in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """No produced key: this step is the flow's endpoint."""
        return set()
