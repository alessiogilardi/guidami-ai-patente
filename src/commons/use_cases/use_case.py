from abc import ABC, abstractmethod
from typing import final


class UseCase[T_In, T_Out](ABC):
    """Contratto sincrono per un caso d'uso con input e output tipizzati."""

    @final
    def __call__(self, request: T_In) -> T_Out:
        """Invoca il caso d'uso delegando a `execute`.

        Args:
            request: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        return self.execute(request)

    @abstractmethod
    def execute(self, request: T_In) -> T_Out:
        """Esegue la logica principale del caso d'uso.

        Args:
            request: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        ...


class AsyncUseCase[T_In, T_Out](ABC):
    """Contratto asincrono per un caso d'uso con input e output tipizzati."""

    @final
    async def __call__(self, request: T_In) -> T_Out:
        """Invoca il caso d'uso delegando a `execute`.

        Args:
            request: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        return await self.execute(request)

    @abstractmethod
    async def execute(self, request: T_In) -> T_Out:
        """Esegue la logica principale del caso d'uso.

        Args:
            request: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        ...
