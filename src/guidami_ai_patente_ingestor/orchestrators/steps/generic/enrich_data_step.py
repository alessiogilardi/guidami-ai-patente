import logging
from typing import cast

from pydantic import BaseModel

from commons.flowstep import FlowContext, Step

from .protocols.enricher_protocol import EnricherProtocol

logger = logging.getLogger(__name__)


class EnrichDataStep[T: BaseModel](Step):
    """Applica una catena di enricher all'intera lista presente nel contesto.

    Ogni enricher opera sull'intera lista in un'unica chiamata (list-in/list-out),
    non item per item: necessario per enricher che devono deduplicare o aggregare
    informazioni sull'intero batch prima di restituire il risultato (es. una sola
    chiamata vision LLM per immagine unica, condivisa da più item).

    Args:
        name: Nome univoco dello step nel flow.
        enrichers: Catena ordinata di enricher; lista vuota → passthrough.
        input_key: Chiave da cui leggere la lista sorgente nel `FlowContext`.
        output_key: Chiave in cui scrivere la lista arricchita nel `FlowContext`.
    """

    def __init__(
        self,
        name: str,
        enrichers: list[EnricherProtocol[T, T]],
        input_key: str,
        output_key: str,
    ) -> None:
        """Inietta nome, catena di enricher, input key e output key."""
        super().__init__(name)
        self._enrichers = enrichers
        self._input_key = input_key
        self._output_key = output_key

    def execute(self, context: FlowContext) -> None:
        """Legge ``input_key``, applica la catena di enricher, scrive in ``output_key``.

        Args:
            context: Shared pipeline context.
        """
        items = cast(list[T], context.get(self._input_key))
        context.put(self._output_key, self.enrich(items))

    def get_required_keys(self) -> set[str]:
        """Richiede ``input_key`` nel contesto."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produce ``output_key`` nel contesto."""
        return {self._output_key}

    def enrich(self, items: list[T]) -> list[T]:
        """Applica ogni enricher della catena all'intera lista, in ordine.

        Args:
            items: Lista sorgente da arricchire.

        Returns:
            Lista risultante dopo l'applicazione in sequenza di tutti gli enricher.
        """
        for enricher in self._enrichers:
            items = enricher.enrich(items)
        return items
