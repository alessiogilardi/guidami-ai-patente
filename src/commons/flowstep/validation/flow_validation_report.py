"""Flow validation report."""

from .models import StepValidationResult


class FlowValidationReport:
    """Aggregated report of all validation results for a pipeline."""

    def __init__(self) -> None:
        """Inizializza un report vuoto senza risultati né chiavi richieste."""
        self._results: list[StepValidationResult] = []
        self._required_input_keys: set[str] = set()

    @property
    def required_input_keys(self) -> set[str]:
        """Chiavi di input richieste dal pipeline prima dell'esecuzione."""
        return self._required_input_keys.copy()

    def set_required_input_keys(self, keys: set[str]) -> None:
        """Imposta le chiavi di input richieste dal pipeline.

        Args:
            keys: Insieme di chiavi richieste.
        """
        self._required_input_keys = set(keys)

    def add_result(self, result: StepValidationResult) -> None:
        """Add a result to the report.

        Args:
            result: Validation result to add
        """
        self._results.append(result)

    def add_results(self, results: list[StepValidationResult]) -> None:
        """Add multiple results to the report.

        Args:
            results: List of results to add
        """
        self._results.extend(results)

    def has_errors(self) -> bool:
        """Return True if there are any ERROR-level results."""
        return any(r.is_error() for r in self._results)

    def has_warnings(self) -> bool:
        """Return True if there are any WARNING-level results."""
        return any(r.is_warning() for r in self._results)

    def get_errors(self) -> list[StepValidationResult]:
        """Return only ERROR-level results."""
        return [r for r in self._results if r.is_error()]

    def get_warnings(self) -> list[StepValidationResult]:
        """Return only WARNING-level results."""
        return [r for r in self._results if r.is_warning()]

    def get_all_results(self) -> list[StepValidationResult]:
        """Return a copy of all results."""
        return self._results.copy()

    def to_dict(self) -> dict:
        """Serialize the report to a dictionary."""
        return {
            "has_errors": self.has_errors(),
            "has_warnings": self.has_warnings(),
            "error_count": len(self.get_errors()),
            "warning_count": len(self.get_warnings()),
            "required_input_keys": sorted(self._required_input_keys),
            "results": [r.to_dict() for r in self._results],
        }

    def __str__(self) -> str:
        """Rappresentazione leggibile del report con errori e warning."""
        lines = ["Flow Validation Report"]
        lines.append("=" * 50)

        if self._required_input_keys:
            keys = ", ".join(sorted(self._required_input_keys))
            lines.append(f"\nREQUIRED INPUT KEYS: {keys}")

        errors = self.get_errors()
        warnings = self.get_warnings()

        if errors:
            lines.append(f"\nERRORS ({len(errors)}):")
            for err in errors:
                lines.append(f"  [{err.step_name}] {err.message}")

        if warnings:
            lines.append(f"\nWARNINGS ({len(warnings)}):")
            for warn in warnings:
                lines.append(f"  [{warn.step_name}] {warn.message}")

        if not errors and not warnings:
            lines.append("\n✓ No issues found")

        return "\n".join(lines)
