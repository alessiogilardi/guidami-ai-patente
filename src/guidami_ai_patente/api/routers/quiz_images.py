"""Quiz image endpoint: bytes for a database-referenced filename."""

import asyncio

from fastapi import APIRouter, Response
from pywire import Autowired

from guidami_ai_patente.services import QuizImageService

router = APIRouter(prefix="/quiz-images", tags=["quiz-images"])


@router.get("/{filename}")
async def get_quiz_image(filename: str, service: Autowired[QuizImageService]) -> Response:
    """Returns the bytes of a referenced quiz image (FR-12).

    The service validates the name against `quiz_questions.image_filename` before any
    filesystem access, so an unreferenced name — including a traversal attempt — is a
    404 raised in the domain layer and rendered by the global handler (AD-24).
    """
    image = await asyncio.to_thread(service, filename)
    return Response(content=image.content, media_type=image.media_type)
