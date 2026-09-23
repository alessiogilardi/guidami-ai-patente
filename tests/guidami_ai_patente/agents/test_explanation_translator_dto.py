"""spec 0018: the translator's own field constraints — non-empty in, non-empty out."""

import pytest
from pydantic import ValidationError
from pywire import get_default_container

from commons.ai.agents.utils.prompt_renderer import PromptRenderer
from guidami_ai_patente.agents.explanation_translator.dto import (
    ExplanationTranslatorRequest,
    ExplanationTranslatorResponse,
)
from guidami_ai_patente.models import TranslationHint
from guidami_ai_patente.repositories import AgentConfigRepository


def test_text_is_required() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorRequest()  # type: ignore[call-arg]


def test_an_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorRequest(text="")


def test_a_non_empty_text_is_accepted() -> None:
    request = ExplanationTranslatorRequest(text="La sosta è vietata.")

    assert request.text == "La sosta è vietata."


def test_an_empty_translated_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExplanationTranslatorResponse(translated_text="")


def test_a_non_empty_translated_text_is_accepted() -> None:
    response = ExplanationTranslatorResponse(translated_text="Остановка запрещена.")

    assert response.translated_text == "Остановка запрещена."


def test_hints_default_to_empty() -> None:
    request = ExplanationTranslatorRequest(text="La sosta è vietata.")

    assert request.hints == ()


def test_hints_block_is_empty_with_no_hints() -> None:
    request = ExplanationTranslatorRequest(text="La sosta è vietata.")

    assert request.hints_block == ""


def test_hints_block_renders_one_hint() -> None:
    request = ExplanationTranslatorRequest(
        text="La carreggiata è stretta.",
        hints=(TranslationHint(term="carreggiata", term_ru="проезжая часть"),),
    )

    assert request.hints_block == (
        '\n\nTraduzioni richieste per termini specifici:\n- "carreggiata" → "проезжая часть"'
    )


def test_hints_block_renders_multiple_hints_one_per_line() -> None:
    request = ExplanationTranslatorRequest(
        text="La carreggiata e la banchina.",
        hints=(
            TranslationHint(term="carreggiata", term_ru="проезжая часть"),
            TranslationHint(term="banchina", term_ru="обочина"),
        ),
    )

    assert request.hints_block == (
        "\n\nTraduzioni richieste per termini specifici:\n"
        '- "carreggiata" → "проезжая часть"\n'
        '- "banchina" → "обочина"'
    )


def test_the_rendered_prompt_with_no_hints_is_byte_identical_to_before_fr8(
    api_client: object,
) -> None:
    """Regression for FR-8's backward-compatibility clause (grilling round, 2026-09-23).

    Renders the *real* `configs/agents/explanation_translator.yaml` `user` template —
    not a copy — so a future edit to that file that reintroduces a stray blank line is
    caught here, not just by reading the YAML.
    """
    config = get_default_container().resolve(AgentConfigRepository).load("explanation_translator")
    renderer = PromptRenderer(config.user)
    request = ExplanationTranslatorRequest(text="La sosta è vietata.")

    rendered = renderer.render(request)

    assert rendered == (
        "Traduci in russo il seguente testo.\n\n<testo>\nLa sosta è vietata.\n</testo>\n"
    )
