from glossary.utils import capitalize_definition, normalize_term


def test_normalize_term_uppercases_a_lowercase_term() -> None:
    assert normalize_term("arresto") == "ARRESTO"


def test_normalize_term_uppercases_a_mixed_case_multi_word_term() -> None:
    assert normalize_term("Area di intersezione") == "AREA DI INTERSEZIONE"


def test_normalize_term_leaves_an_already_uppercase_term_unchanged() -> None:
    assert normalize_term("ATTRAVERSAMENTO PEDONALE") == "ATTRAVERSAMENTO PEDONALE"


def test_capitalize_definition_uppercases_a_lowercase_first_letter() -> None:
    assert capitalize_definition("l'interruzione della marcia") == "L'interruzione della marcia"


def test_capitalize_definition_leaves_the_rest_of_the_text_untouched() -> None:
    assert capitalize_definition("area destinata alla circolazione") == (
        "Area destinata alla circolazione"
    )


def test_capitalize_definition_leaves_an_already_capitalized_definition_unchanged() -> None:
    assert (
        capitalize_definition("Parte della carreggiata riservata ai pedoni")
        == "Parte della carreggiata riservata ai pedoni"
    )


def test_capitalize_definition_of_an_empty_string_stays_empty() -> None:
    assert capitalize_definition("") == ""
