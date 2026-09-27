"""Tests for normalize_term_casing: consistent display casing across glossary sources.

DB-sourced terms are stored ALL CAPS by the build pipeline (`normalize_term`), while
`GlossaryEnricherAgent`'s live terms preserve the question's own casing — mixing both
in the same `translation_hints` list otherwise looks inconsistent to the end user.
"""

from guidami_ai_patente.utils import normalize_term_casing


def test_an_all_caps_single_word_term_is_sentence_cased() -> None:
    assert normalize_term_casing("VEICOLO") == "Veicolo"


def test_an_all_caps_multi_word_term_is_sentence_cased() -> None:
    assert normalize_term_casing("VEICOLO A MOTORE") == "Veicolo a motore"


def test_an_already_lowercase_term_gets_its_first_letter_capitalized() -> None:
    assert normalize_term_casing("patente di guida") == "Patente di guida"


def test_surrounding_whitespace_is_stripped() -> None:
    assert normalize_term_casing("  targa  ") == "Targa"


def test_an_already_sentence_cased_term_is_left_unchanged() -> None:
    assert normalize_term_casing("Carreggiata") == "Carreggiata"
