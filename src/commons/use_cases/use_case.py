from abc import ABC, abstractmethod
from typing import final


class UseCase[T_In, T_Out](ABC):
    """Synchronous contract for a use case with typed input and output."""

    @final
    def __call__(self, request: T_In) -> T_Out:
        """Invokes the use case, delegating to `execute`.

        Args:
            request: Input data for the use case.

        Returns:
            Result produced by the use case.
        """
        return self.execute(request)

    @abstractmethod
    def execute(self, request: T_In) -> T_Out:
        """Executes the main logic of the use case.

        Args:
            request: Input data for the use case.

        Returns:
            Result produced by the use case.
        """
        ...


class AsyncUseCase[T_In, T_Out](ABC):
    """Asynchronous contract for a use case with typed input and output."""

    @final
    async def __call__(self, request: T_In) -> T_Out:
        """Invokes the use case, delegating to `execute`.

        Args:
            request: Input data for the use case.

        Returns:
            Result produced by the use case.
        """
        return await self.execute(request)

    @abstractmethod
    async def execute(self, request: T_In) -> T_Out:
        """Executes the main logic of the use case.

        Args:
            request: Input data for the use case.

        Returns:
            Result produced by the use case.
        """
        ...
