"""Step generico che carica una lista di modelli da disco tramite JsonRepository.

Domain-agnostic: parametrizzato dal tipo del modello e dalla chiave di contesto.
"""

import logging
from typing import cast

from commons.repositories import JsonRepository
from flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadJsonStep[T](Step):
    """Carica una lista di modelli da disco e la espone nel contesto con una data chiave.

    Args:
        name:           Nome univoco dello step nel flow.
        input_layer:    Nome del layer di input (es. ``"parsed"``, ``"cleaned"``).
        source:         Chiave della source da caricare (es. ``"cds"``, ``"quiz"``).
        output_key:     Chiave del ``FlowContext`` in cui scrivere la lista.
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        repository:     Repository iniettato, già mappato sul modello da caricare.
    """

    def __init__(
        self,
        name: str,
        input_layer: str,
        source: str,
        output_key: str,
        layer_resolver: LayerResolver,
        repository: JsonRepository[T],
    ) -> None:
        """Inietta layer/source/chiave di contesto, poi resolver e repository."""
        super().__init__(name)
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._source = source
        self._repository = repository
        self._output_key = output_key

    def execute(self, context: FlowContext) -> None:
        """Risolve il path, carica la lista e la scrive nel contesto."""
        path = self._layer_resolver.path(self._input_layer, self._source)
        items = cast(list[T], self._repository.load(path))
        logger.info("Loaded %d items for source '%s' via LoadJsonStep", len(items), self._source)

        context.put(self._output_key, items)

    def get_required_keys(self) -> set[str]:
        """Nessuna chiave richiesta: questo step è il punto di partenza del flow."""
        return set()

    def get_produced_keys(self) -> set[str]:
        """Produce la chiave configurata ``output_key``."""
        return {self._output_key}
