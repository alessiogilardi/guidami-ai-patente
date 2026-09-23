"""Explanation translation endpoint (spec 0018): IT -> RU, decoupled from the RAG pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pywire import Autowired

from domain.entities.users import UserEntity
from guidami_ai_patente.models import TranslationHint, TranslationRequest
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
    """Translates `request.text` to Russian, honoring any `request.hints` (FR-1, FR-8).

    Takes no `{number}`: the client already holds the Italian text from its own
    prior `GET /quiz-questions/{number}/explanation` call and passes it directly
    (AD-1) — this endpoint never re-reads or recomputes it.
    """
    translation_request = TranslationRequest(
        text=request.text,
        hints=tuple(
            TranslationHint(term=hint.term, term_ru=hint.term_ru) for hint in request.hints
        ),
    )
    translated_text = await service(translation_request)
    return ExplanationTranslationResponse(translated_text=translated_text)
