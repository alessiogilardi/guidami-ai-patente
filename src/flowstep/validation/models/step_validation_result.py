"""Risultato di validazione."""

from dataclasses import dataclass

from ..enums import ValidationSeverity


@dataclass(frozen=True)
class StepValidationResult:
    """Risultato di una singola validazione.

    Attributes:
        severity: Livello di gravità del risultato
        message: Descrizione del problema o avviso
        step_name: Nome dello step che ha generato il risultato
        context_key: Chiave del context coinvolta (opzionale)
    """

    severity: ValidationSeverity
    message: str
    step_name: str
    context_key: str | None = None

    def is_error(self) -> bool:
        """Verifica se il risultato è un errore bloccante.

        Returns:
            True se è un errore, False altrimenti
        """
        return self.severity is ValidationSeverity.ERROR

    def is_warning(self) -> bool:
        """Verifica se il risultato è un warning.

        Returns:
            True se è un warning, False altrimenti
        """
        return self.severity is ValidationSeverity.WARNING

    def to_dict(self) -> dict:
        """Serializza il risultato in dizionario.

        Returns:
            Dizionario con i dati del risultato
        """
        return {
            "severity": self.severity.value,
            "message": self.message,
            "step_name": self.step_name,
            "context_key": self.context_key,
        }
