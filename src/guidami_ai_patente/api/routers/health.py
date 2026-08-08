"""Liveness probe endpoint."""

from fastapi import APIRouter

from ..schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Returns service liveness status."""
    return HealthResponse(status="ok")
