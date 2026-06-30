"""Enumerazioni per il sistema di validazione."""

from enum import StrEnum


class ValidationSeverity(StrEnum):
    """Livello di gravità di un risultato di validazione.

    Attributes:
        ERROR: Errore bloccante che impedisce l'esecuzione della pipeline
        WARNING: Avviso non bloccante
    """

    ERROR = "error"
    WARNING = "warning"
