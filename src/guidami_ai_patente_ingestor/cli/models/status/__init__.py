"""Status DTOs for the `ingest status` command (CLI-local, see `cli-structure.md`)."""

from .command_readiness import CommandReadiness
from .readiness_state import ReadinessState
from .source_readiness import SourceReadiness
from .status_report import StatusReport
from .table_health import TableHealth

__all__ = [
    "CommandReadiness",
    "ReadinessState",
    "SourceReadiness",
    "StatusReport",
    "TableHealth",
]
