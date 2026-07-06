"""Step generico che scrive una lista di modelli su disco tramite JsonRepository.

Domain-agnostic: parametrizzato dal tipo del modello e dalla chiave di contesto.
"""

import logging
from typing import cast

from commons.repositories import JsonRepository
from flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class WriteJsonStep[T](Step):
    """Scrive una lista di modelli su disco per una data (layer, source).

    Args:
        name:           Nome univoco dello step nel flow.
        output_layer:   Nome del layer di output (es. ``"cleaned"``, ``"enriched"``).
        source:         Chiave della source da scrivere (es. ``"cds"``, ``"quiz"``).
        input_key:      Chiave del ``FlowContext`` da cui leggere la lista.
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        repository:     Repository iniettato, già mappato sul modello da scrivere.
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
        """Inietta layer/source/chiave di contesto, poi resolver e repository."""
        super().__init__(name)
        self._layer_resolver = layer_resolver
        self._output_layer = output_layer
        self._source = source
        self._repository = repository
        self._input_key = input_key

    def execute(self, context: FlowContext) -> None:
        """Legge la lista dal contesto e la scrive sul path risolto."""
        items = cast(list[T], context.get(self._input_key))
        path = self._layer_resolver.path(self._output_layer, self._source)
        self._repository.write(items, path)

        logger.info(
            "WriteJsonStep: wrote %d items for source '%s'",
            len(items),
            self._source,
        )

    def get_required_keys(self) -> set[str]:
        """Richiede ``input_key`` nel contesto."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Nessuna chiave prodotta: questo step è il punto di arrivo del flow."""
        return set()
