"""Quiz image endpoint: bytes for a database-referenced filename."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pywire import Autowired

from domain.entities.users import UserEntity
from guidami_ai_patente.services import QuizImageService

from ..dependencies.user_identity import require_registered_user

router = APIRouter(prefix="/quiz-images", tags=["quiz-images"])


@router.get("/{filename}")
async def get_quiz_image(
    filename: str,
    user: Annotated[UserEntity, Depends(require_registered_user)],
    service: Autowired[QuizImageService],
) -> Response:
    """Returns the bytes of a referenced quiz image (FR-12), now gated by FR-3.

    The service validates the name against `quiz_questions.image_filename` before any
    filesystem access, so an unreferenced name — including a traversal attempt — is a
    404 raised in the domain layer and rendered by the global handler (AD-24).

    `user` is declared before `service`: pywire's `_wire_endpoint` gives a bare
    `Autowired[T]` parameter a real Python-level default (`Depends(...)`), while
    `user`'s `Annotated[X, Depends(...)]` form has none at the raw signature level.
    FastAPI/pywire resolve dependencies by name, not position, so this reordering is
    behavior-preserving — but Python itself rejects a signature where a required
    parameter follows a defaulted one.
    """
    image = await asyncio.to_thread(service, filename)
    return Response(content=image.content, media_type=image.media_type)
