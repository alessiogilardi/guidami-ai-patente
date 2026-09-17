"""GET /me: registration status, provisioning the caller on first contact."""

from typing import Annotated

from fastapi import APIRouter, Depends

from domain.entities.users import UserEntity

from ..dependencies.user_identity import resolve_identity
from ..schemas.me import MeResponse

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: Annotated[UserEntity, Depends(resolve_identity)]) -> MeResponse:
    """Reports registration status, provisioning the row if this is the first contact.

    Uses `resolve_identity` alone, never `require_registered_user`: "not yet approved"
    is itself a valid, successful answer for this endpoint (FR-2) — it never returns
    403.
    """
    return MeResponse(registered=user.registered)
