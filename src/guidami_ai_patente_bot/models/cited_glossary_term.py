"""The Italian/Russian glossary term the bot received from the API (spec 0020)."""

from pydantic import BaseModel, ConfigDict


class CitedGlossaryTerm(BaseModel):
    """A bot-local mirror of the API's `CitedGlossaryTerm` shape.

    Kept as its own bot-side class (not a re-import of `guidami_ai_patente`'s), matching
    this package's existing convention of never importing across the API/bot process
    boundary (`QuizExplanation` vs. `QuizExplanationResponse` is the precedent). Named
    `CitedGlossaryTerm`, not `TranslationHint`: this project has no bot-side
    `TranslationHint` at all (spec 0018's hints are constructed inline, as a plain dict,
    at the point `QuizApiClient.translate_explanation` forwards them — Task 10).
    """

    model_config = ConfigDict(frozen=True)

    term: str
    definition: str
    term_ru: str
