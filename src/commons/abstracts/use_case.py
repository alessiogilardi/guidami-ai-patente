from abc import ABC, abstractmethod


class UseCase[T_In, T_Out](ABC):
    """Contratto generico per un caso d'uso con input e output tipizzati."""

    def __call__(self, input: T_In) -> T_Out:
        """Invoca il caso d'uso delegando a `execute`.

        Args:
            input: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        return self.execute(input)

    @abstractmethod
    def execute(self, input: T_In) -> T_Out:
        """Esegue la logica principale del caso d'uso.

        Args:
            input: Dato di input per il caso d'uso.

        Returns:
            Risultato prodotto dal caso d'uso.
        """
        ...
