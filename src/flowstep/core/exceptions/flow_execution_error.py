from ._base_flow_error import BaseFlowError


class FlowExecutionError(BaseFlowError):
    """Exception raised during pipeline execution.

    Attributes:
        step_name: Name of the step that caused the error
        original_error: Original exception
    """

    def __init__(self, step_name: str, original_error: Exception):
        """Initialize the exception with step details.

        Args:
            step_name: Name of the step that failed
            original_error: Original exception raised by the step
        """
        self.step_name = step_name
        self.original_error = original_error
        super().__init__(f"Error executing step '{step_name}': {str(original_error)}")
