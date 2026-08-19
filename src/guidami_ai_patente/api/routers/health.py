"""Liveness probe endpoint."""

from fastapi import APIRouter
from pywire import Autowired

from guidami_ai_patente.services.health_check_service import HealthCheckService

from ..schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(service: Autowired[HealthCheckService]) -> HealthResponse:
    """Returns service liveness status and the resolved pywire version."""
    return HealthResponse(status=service.check(), pywire_version=service.pywire_version())
