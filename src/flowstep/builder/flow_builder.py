"""Builder for fluent pipeline construction."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel

from ..core import Flow, FlowContext, Step
from ..validation import FlowValidator
from ..validation.exceptions import FlowValidationError


class FlowBuilder:
    """Builder for fluent pipeline construction.

    Allows building pipelines in a readable and intuitive way using a
    fluent API. When validate=True, runs FlowValidator (structure and
    key-name checks) before returning the Flow.

    Example:
        >>> flow = (
        ...     FlowBuilder("my_pipeline")
        ...     .add_step(LoadStep("load"))
        ...     .add_step(TransformStep("transform"))
        ...     .build(validate=True)
        ... )
    """

    def __init__(self, pipeline_name: str) -> None:
        """Initialize the builder.

        Args:
            pipeline_name: Name of the pipeline to build.
        """
        self._name = pipeline_name
        self._steps: list[Step] = []

    def add_step(self, step: Step) -> Self:
        """Add a step to the pipeline.

        Args:
            step: Step to add.

        Returns:
            Self to allow method chaining.
        """
        self._steps.append(step)
        return self

    def build(
        self,
        validate: bool = False,
        initial_context: FlowContext | dict | None = None,
        initial_context_model: type[BaseModel] | None = None,
    ) -> Flow:
        """Build the pipeline.

        Args:
            validate: If True, runs structural validation before returning.
                Raises on any ERROR-level finding.
            initial_context: Optional context used during key-name validation.
                Keys are extracted and passed as initial_keys.
            initial_context_model: Optional Pydantic model describing the
                types of keys in the initial context.

        Returns:
            Configured pipeline.

        Raises:
            FlowValidationError: If validate=True and any ERROR is found.
        """
        flow = Flow(self._name, self._steps)

        if validate:
            report = FlowValidator().validate(
                flow,
                initial_keys=set(initial_context.keys()) if initial_context else None,
            )

            if report.has_errors():
                raise FlowValidationError(report)

        return flow
