from typing import Protocol

from pydantic import BaseModel


class EnricherProtocol[T_In: BaseModel, T_Out: BaseModel](Protocol):
    """Protocollo per gli enricher di dominio applicati nelle pipeline di preparation.

    Ogni enricher riceve una lista di item da arricchire e restituisce
    la lista arricchita nello stesso ordine.
    """

    def enrich(self, items: list[T_In]) -> list[T_Out]:
        """Applica la logica di arricchimento agli item forniti.

        Args:
            items: Lista di item da arricchire.

        Returns:
            Lista arricchita nello stesso ordine degli input.
        """
        ...
