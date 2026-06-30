"""Validator for Flow pipelines."""

from collections.abc import Iterable

from ..core import Flow
from .enums import ValidationSeverity
from .flow_validation_report import FlowValidationReport
from .models.step_validation_result import StepValidationResult


class FlowValidator:
    """Validate pipeline structure and input contract before execution."""

    def validate(self, flow: Flow, initial_keys: set[str] | None = None) -> FlowValidationReport:
        """Validate pipeline structure and, optionally, input keys.

        Args:
            flow: Pipeline to validate.
            initial_keys: Optional set of keys available in initial context.

        Returns:
            Aggregated validation report.
        """
        if initial_keys is None:
            return self.validate_structure(flow)
        return self.validate_with_context(flow, initial_keys)

    def validate_structure(self, flow: Flow) -> FlowValidationReport:
        """Validate static pipeline structure without initial context.

        This mode computes the external input contract (required_input_keys)
        and does not fail for keys that can come from the initial context.
        """
        report = FlowValidationReport()
        available_keys: set[str] = set()
        required_input_keys: set[str] = set()
        seen_step_names: set[str] = set()

        for step in flow.get_steps():
            if step.name in seen_step_names:
                report.add_result(
                    StepValidationResult(
                        severity=ValidationSeverity.ERROR,
                        message="Duplicate step name detected.",
                        step_name=step.name,
                    )
                )
            seen_step_names.add(step.name)

            required_keys = self._extract_keys(step, "get_required_keys", report)
            produced_keys = self._extract_keys(step, "get_produced_keys", report)

            missing = required_keys - available_keys
            if missing:
                required_input_keys.update(missing)
                for key in sorted(missing):
                    report.add_result(
                        StepValidationResult(
                            severity=ValidationSeverity.WARNING,
                            message=(
                                "Required key is not produced by previous steps and "
                                "must be provided by initial context."
                            ),
                            step_name=step.name,
                            context_key=key,
                        )
                    )

            overwritten = produced_keys & available_keys
            for key in sorted(overwritten):
                report.add_result(
                    StepValidationResult(
                        severity=ValidationSeverity.WARNING,
                        message="Produced key overwrites an already available key.",
                        step_name=step.name,
                        context_key=key,
                    )
                )

            available_keys.update(produced_keys)
            self._run_custom_validation(step, report)

        report.set_required_input_keys(required_input_keys)
        return report

    def validate_with_context(self, flow: Flow, initial_keys: set[str]) -> FlowValidationReport:
        """Validate pipeline against explicit initial context keys."""
        report = self.validate_structure(flow)
        missing_from_context = report.required_input_keys - set(initial_keys)

        for key in sorted(missing_from_context):
            report.add_result(
                StepValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message="Required input key is missing from initial context.",
                    step_name="__flow__",
                    context_key=key,
                )
            )

        return report

    def _extract_keys(
        self,
        step,
        method_name: str,
        report: FlowValidationReport,
    ) -> set[str]:
        try:
            raw_keys = getattr(step, method_name)()
        except Exception as exc:
            report.add_result(
                StepValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message=f"{method_name}() raised an exception: {exc}",
                    step_name=step.name,
                )
            )
            return set()

        if not isinstance(raw_keys, set):
            report.add_result(
                StepValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message=f"{method_name}() must return set[str].",
                    step_name=step.name,
                )
            )
            return set()

        invalid_values = [key for key in raw_keys if not isinstance(key, str)]
        for invalid_key in invalid_values:
            report.add_result(
                StepValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message=f"{method_name}() contains a non-string key.",
                    step_name=step.name,
                    context_key=str(invalid_key),
                )
            )

        return {key for key in raw_keys if isinstance(key, str)}

    def _run_custom_validation(
        self,
        step,
        report: FlowValidationReport,
    ) -> None:
        custom_validate = getattr(step, "validate", None)
        if not callable(custom_validate):
            return

        try:
            custom_result = custom_validate()
        except Exception as exc:
            report.add_result(
                StepValidationResult(
                    severity=ValidationSeverity.ERROR,
                    message=f"Custom validate() raised an exception: {exc}",
                    step_name=step.name,
                )
            )
            return

        if custom_result is None:
            return

        if isinstance(custom_result, StepValidationResult):
            report.add_result(custom_result)
            return

        if isinstance(custom_result, Iterable):
            normalized = list(custom_result)
            if all(isinstance(result, StepValidationResult) for result in normalized):
                report.add_results(normalized)
                return

        report.add_result(
            StepValidationResult(
                severity=ValidationSeverity.WARNING,
                message="Custom validate() returned an unsupported result type.",
                step_name=step.name,
            )
        )
