from pydantic import BaseModel, ConfigDict


class TableHealth(BaseModel):
    """Existence and row count of a DB table, read online only (`--online`)."""

    model_config = ConfigDict(frozen=True)

    table: str
    exists: bool
    row_count: int | None
