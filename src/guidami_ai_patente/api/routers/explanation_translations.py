"""Explanation translation endpoint (spec 0018): IT -> RU, decoupled from the RAG pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pywire import Autowired

from domain.entities.users import UserEntity
from guidami_ai_patente.services import ExplanationTranslationService

from ..dependencies.language import require_supported_language
from ..dependencies.user_identity import require_registered_user
from ..schemas.explanation_translation import (
    ExplanationTranslationRequest,
    ExplanationTranslationResponse,
)

router = APIRouter(prefix="/explanations", tags=["explanation-translations"])

_RequireRegisteredUser = Annotated[UserEntity, Depends(require_registered_user)]
_RequireSupportedLanguage = Annotated[str, Depends(require_supported_language)]


@router.post("/translate", response_model=ExplanationTranslationResponse)
async def translate_explanation(
    request: ExplanationTranslationRequest,
    user: _RequireRegisteredUser,
    lang: _RequireSupportedLanguage,
    service: Autowired[ExplanationTranslationService],
) -> ExplanationTranslationResponse:
    """Translates `request.text` to Russian (spec 0018, FR-1).

    Takes no `{number}`: the client already holds the Italian text from its own
    prior `GET /quiz-questions/{number}/explanation` call and passes it directly
    (AD-1) — this endpoint never re-reads or recomputes it.
    """
    translated_text = await service(request.text)
    return ExplanationTranslationResponse(translated_text=translated_text)
