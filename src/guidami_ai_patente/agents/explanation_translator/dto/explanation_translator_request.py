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
        r"""Renders `hints` as a labeled block for the `$hints_block` template slot.

        Empty when there are no hints (FR-8's backward-compatibility clause): the
        template attaches `$hints_block` directly after `</testo>` with no line of
        its own (see the YAML below), so an empty string here makes the rendered
        prompt genuinely byte-identical to before this field existed — not just
        similar (grilling round, 2026-09-23; see
        `test_the_rendered_prompt_with_no_hints_is_byte_identical_to_before_fr8`).

        The leading `"\n\n"` when hints are present supplies the blank-line
        separator from `</testo>` itself, matching the blank line already used
        elsewhere in this prompt (e.g. before `<testo>`).
        """
        if not self.hints:
            return ""
        lines = "\n".join(f'- "{hint.term}" → "{hint.term_ru}"' for hint in self.hints)
        return f"\n\nTraduzioni richieste per termini specifici:\n{lines}"
