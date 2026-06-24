"""Step generico che carica una lista di modelli da disco tramite JsonRepository.

Domain-agnostic: parametrizzato dal tipo del modello e dalla chiave di contesto.
"""

import logging
from typing import cast

from commons.flowstep import FlowContext, Step
from guidami_ai_patente_ingestor.repositories.json import JsonRepository
from guidami_ai_patente_ingestor.services import LayerResolver

logger = logging.getLogger(__name__)


class LoadJsonStep[T](Step):
    """Carica una lista di modelli da disco e la espone nel contesto con una data chiave.

    Args:
        name:           Nome univoco dello step nel flow.
        layer_resolver: Resolver che mappa (layer, source) → Path del file JSON.
        input_layer:    Nome del layer di input (es. ``"parsed"``, ``"cleaned"``).
        source:         Chiave della source da caricare (es. ``"cds"``, ``"quiz"``).
        model_class:    Classe Pydantic del modello (usata al solo scopo di
                        ottenere l'istanza di ``JsonRepository``).
        output_key:     Chiave del ``FlowContext`` in cui scrivere la lista.
    """

    def __init__(
        self,
        name: str,
        layer_resolver: LayerResolver,
        input_layer: str,
        source: str,
        model_class: type[T],
        output_key: str,
    ) -> None:
        """Inietta resolver, layer/source, model class e chiave di contesto."""
        super().__init__(name)
        self._layer_resolver = layer_resolver
        self._input_layer = input_layer
        self._source = source
        self._model_class = model_class
        self._repository = JsonRepository.get_instance(self._model_class)
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
