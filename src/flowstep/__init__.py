"""FlowStep — Data processing pipeline management system.

Example:
    >>> from flowstep import Flow, Step, FlowContext, FlowBuilder
    >>>
    >>> pipeline = (FlowBuilder("my_pipeline")
    ...     .add_step(LoadDataStep())
    ...     .add_step(ProcessDataStep())
    ...     .build())
    >>>
    >>> result = pipeline.run({"input": "data"})
"""

from .builder import FlowBuilder
from .core import Flow, FlowContext, Step
from .core.exceptions import FlowExecutionError
from .steps import ApplyStep
from .validation import (
    FlowValidationError,
    FlowValidationReport,
    FlowValidator,
    StepValidationResult,
    ValidationSeverity,
)

__all__ = [
    "ApplyStep",
    "FlowBuilder",
    "Step",
    "Flow",
    "FlowContext",
    "FlowExecutionError",
    "ValidationSeverity",
    "StepValidationResult",
    "FlowValidationReport",
    "FlowValidator",
    "FlowValidationError",
]
