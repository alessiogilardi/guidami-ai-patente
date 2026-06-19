from ...core.exceptions._base_flow_error import BaseFlowError
from ..flow_validation_report import FlowValidationReport


class FlowValidationError(BaseFlowError):
    """Raised when flow validation fails.

    Attributes:
        report: Validation report with error details
    """

    def __init__(self, report: FlowValidationReport):
        """Initialize with the validation report.

        Args:
            report: FlowValidationReport with the errors
        """
        self.report = report
        error_count = len(report.get_errors())
        super().__init__(
            f"Flow validation failed with {error_count} error(s). See report for details."
        )
