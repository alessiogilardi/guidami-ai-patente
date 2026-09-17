"""Resolves and gates on the caller's Telegram identity (spec 0016, FR-1, FR-2, FR-3).

`resolve_identity`/`require_registered_user` are ordinary FastAPI dependency
functions, not pywire components: pywire's FastAPI integration only rewrites bare
`Autowired[T]` parameters on the route's own top-level callable
(`pywire.fastapi._wire_endpoint`, invoked from a patched `APIRouter.add_api_route`) —
a nested `Depends()` sub-dependency's parameters are never rewritten, so a bare
`Autowired[T]` parameter here would not resolve. FastAPI's own dependency resolution
has no such depth limit, though: `_get_user_repository` is an ordinary hand-written
`Depends()` callable, nested two levels deep (`require_registered_user` depends on
`resolve_identity`, which depends on this), using the exact same container fallback
pywire's own `_resolve_autowired` uses internally, so it still picks up a test's bound
container via `request.app.state.pywire_container` rather than always falling back to
the process-wide default.

`resolve_identity` stays a plain `async def` calling `asyncio.to_thread(repository.provision, ...)`
rather than a sync function wrapped elsewhere, matching every repository's sync-by-
construction posture (AD-10) — see this plan's Global Constraints for why, and for the
deferred note on what a future async-data-layer migration would need to touch beyond
this file (`QuizAnswerChecker` and any `UseCase` shaped like it).
"""

import asyncio
from typing import Annotated

from fastapi import Depends, Header, Request
from pywire import get_default_container

from domain.entities.users import UserEntity
from guidami_ai_patente.exceptions import UnregisteredUserError
from guidami_ai_patente.repositories import UserRepository


def _get_user_repository(request: Request) -> UserRepository:
    container = getattr(request.app.state, "pywire_container", None) or get_default_container()
    return container.resolve(UserRepository)


async def resolve_identity(
    x_telegram_user_id: Annotated[int, Header(alias="X-Telegram-User-Id")],
    repository: Annotated[UserRepository, Depends(_get_user_repository)],
) -> UserEntity:
    """Provisions the caller's `users` row on first contact, never rejects (FR-1, FR-2)."""
    return await asyncio.to_thread(repository.provision, x_telegram_user_id)


async def require_registered_user(
    user: Annotated[UserEntity, Depends(resolve_identity)],
) -> UserEntity:
    """Raises when the caller has not yet been approved (FR-3).

    Built on `resolve_identity` rather than duplicating its provisioning logic, so
    `GET /me` (which uses `resolve_identity` alone) and every other endpoint (which
    uses this) can never provision a row differently depending on which one ran.
    """
    if not user.registered:
        raise UnregisteredUserError(user.telegram_user_id)
    return user
