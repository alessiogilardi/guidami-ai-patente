"""Abstract base class for pipeline steps."""

from abc import ABC, abstractmethod

from ..context import FlowContext


class Step(ABC):
    """Abstract base class for all pipeline steps.

    Each step must implement the abstract methods to define:
    - The execution logic
    - The keys required from the context
    - The keys produced in the context

    Attributes:
        _name: Identifying name of the step
    """

    def __init__(self, name: str):
        """Initialize the step.

        Args:
            name: Name of the step (must be unique in the pipeline)
        """
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def execute(self, context: FlowContext) -> None:
        """Execute the step logic.

        Args:
            context: Shared pipeline context

        Raises:
            Exception: Any exception during execution
        """
        pass

    @abstractmethod
    def get_required_keys(self) -> set[str]:
        """Return the keys required from the context before execution.

        Returns:
            Set of required keys
        """
        pass

    @abstractmethod
    def get_produced_keys(self) -> set[str]:
        """Return the keys produced into the context after execution.

        Returns:
            Set of produced keys
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}')"
