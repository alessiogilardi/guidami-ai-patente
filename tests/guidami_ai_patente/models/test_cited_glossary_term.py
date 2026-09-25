"""Tests for CitedGlossaryTerm — the domain shape spec 0020's cited glossary terms use.

Not `guidami_ai_patente.models.TranslationHint` (spec 0018): that one is the translation
UseCase's 2-field input shape (`term`, `term_ru`), untouched by this spec. This class is
the vocabulary stage's own, richer, citation-resolved shape (grilling round, 2026-09-23).
"""

import pytest
from pydantic import ValidationError

from guidami_ai_patente.enums import GlossaryTermOrigin
from guidami_ai_patente.models import CitedGlossaryTerm


def test_it_is_frozen() -> None:
    term = CitedGlossaryTerm(
        term="carreggiata",
        definition="Parte della strada...",
        term_ru="проезжая часть",
        origin=GlossaryTermOrigin.VERBATIM_CORPUS,
    )
    with pytest.raises(ValidationError):
        term.term = "banchina"  # type: ignore[misc]


def test_an_empty_term_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CitedGlossaryTerm(
            term="", definition="x", term_ru="x", origin=GlossaryTermOrigin.VERBATIM_CORPUS
        )


def test_an_empty_definition_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CitedGlossaryTerm(
            term="carreggiata",
            definition="",
            term_ru="x",
            origin=GlossaryTermOrigin.VERBATIM_CORPUS,
        )


def test_an_empty_term_ru_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CitedGlossaryTerm(
            term="carreggiata",
            definition="x",
            term_ru="",
            origin=GlossaryTermOrigin.VERBATIM_CORPUS,
        )


def test_a_valid_term_is_accepted() -> None:
    term = CitedGlossaryTerm(
        term="carreggiata",
        definition="Parte della strada destinata alla circolazione dei veicoli.",
        term_ru="проезжая часть",
        origin=GlossaryTermOrigin.VERBATIM_CORPUS,
    )
    assert term.term_ru == "проезжая часть"


def test_a_null_term_ru_is_accepted() -> None:
    term = CitedGlossaryTerm(
        term="carreggiata",
        definition="Parte della strada destinata alla circolazione dei veicoli.",
        term_ru=None,
        origin=GlossaryTermOrigin.VERBATIM_CORPUS,
    )
    assert term.term_ru is None


def test_an_agent_generated_origin_is_accepted() -> None:
    """FR-8: an on-demand candidate carries the other origin member."""
    term = CitedGlossaryTerm(
        term="revoca", definition="...", term_ru=None, origin=GlossaryTermOrigin.AGENT_GENERATED
    )
    assert term.origin is GlossaryTermOrigin.AGENT_GENERATED
