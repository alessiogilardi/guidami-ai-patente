from pydantic import BaseModel, ConfigDict

from .command_readiness import CommandReadiness
from .table_health import TableHealth


class StatusReport(BaseModel):
    """Full `ingest status` output: readiness matrix plus optional online table health."""

    model_config = ConfigDict(frozen=True)

    readiness: list[CommandReadiness]
    tables: list[TableHealth] | None
    db_reachable: bool | None
