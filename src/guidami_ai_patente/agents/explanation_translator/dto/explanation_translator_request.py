"""Input of the explanation translator: the Italian text to render in Russian."""

from pydantic import BaseModel, Field, computed_field

from guidami_ai_patente.models import TranslationHint


class ExplanationTranslatorRequest(BaseModel):
    """The Italian text to translate, and any term hints to honor.

    Request DTOs stay documented in English: the value is substituted into the
    user-prompt template, but this docstring is never shipped to the model as
    schema — only `ExplanationTranslatorResponse`'s is.

    Attributes:
        text: The Italian text to translate to Russian.
        hints: Already-reviewed term translations the agent should honor (FR-8).
            Empty by default: a request with no hints renders `hints_block` as an
            empty string, so the template renders exactly as it did before FR-8.
    """

    text: str = Field(min_length=1)
    hints: tuple[TranslationHint, ...] = ()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hints_block(self) -> str:
        """Renders `hints` as a self-contained instruction block for `$hints_block`.

        The full "how to honor a hint" guidance lives here, in the user message,
        rather than as a standing system-prompt rule, so a request with no hints
        leaves the ENTIRE prompt (system + user) byte-identical to before this field
        existed, not just the user template (final-review fix, 2026-09-23).

        Empty when there are no hints (FR-8's backward-compatibility clause).
        """
        if not self.hints:
            return ""
        lines = "\n".join(f'- "{hint.term}" → "{hint.term_ru}"' for hint in self.hints)
        return (
            "\n\nTraduzioni richieste per termini specifici: per ciascun termine elencato "
            "usa sempre la resa russa indicata, adattandola grammaticalmente al contesto "
            "(caso, numero) come farebbe un traduttore umano che consulta un dizionario — "
            "non sostituirla mai con una parola diversa. Alla prima occorrenza di ciascun "
            'termine nel testo tradotto, riportalo come per "Vero"/"Falso": l\'originale '
            "italiano tra virgolette caporali seguito dalla resa russa tra parentesi, es. "
            "«carreggiata» (проезжая часть). Alle occorrenze successive usa solo la resa "
            f"russa, senza ripetere l'originale italiano.\n{lines}"
        )
