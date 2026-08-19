"""Response schema for the health endpoint."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str
    pywire_version: str
