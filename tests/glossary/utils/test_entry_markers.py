from glossary.utils import count_expected_entries, is_abrogated, is_cross_reference


def test_numeric_marker_entries_are_counted() -> None:
    text = "1) ALFA: significato di alfa. 2) Beta: significato di beta."
    assert count_expected_entries(text) == 2


def test_alphabetic_marker_entries_are_counted() -> None:
    text = "si intendono per: a) alfa: uno; b) beta: due; c) gamma: tre."
    assert count_expected_entries(text) == 3


def test_a_leading_preamble_is_not_an_entry() -> None:
    text = "Ai fini delle presenti norme: 1) ALFA: uno. 2) BETA: due."
    assert count_expected_entries(text) == 2


def test_abrogated_entries_are_not_expected() -> None:
    text = "7) ALFA: uno. 7-bis) NUMERO ABROGATO DALLA L. 25 NOVEMBRE 2024, N. 177. 8) BETA: due."
    assert count_expected_entries(text) == 2


def test_cross_reference_only_entries_are_not_expected() -> None:
    text = "4) ALFA: uno. 5) BRACCIO DI INTERSEZIONE: cfr.RAMO DI INTERSEZIONE. 6) BETA: due."
    assert count_expected_entries(text) == 2


def test_an_entry_with_a_parenthesized_cross_reference_and_its_own_definition_counts() -> None:
    text = "35) ALFA: uno. 36) PASSAGGIO PEDONALE (cfr. anche MARCIAPIEDE): parte della strada."
    assert count_expected_entries(text) == 2


def test_nested_sub_items_are_not_counted_as_entries() -> None:
    text = (
        "c) alfa: uno; d) attività riassicurativa: 1) l'assunzione dei rischi. "
        "2) Copertura fornita a un fondo; e) beta: due;"
    )
    assert count_expected_entries(text) == 3


def test_text_without_markers_expects_no_entries() -> None:
    assert count_expected_entries("Testo senza alcuna voce numerata.") == 0


def test_abrogation_markers_are_detected() -> None:
    assert is_abrogated("NUMERO ABROGATO DALLA L. 25 NOVEMBRE 2024, N. 177")
    assert is_abrogated("LETTERA ABROGATA DAL D.LGS. 12 MAGGIO 2015, N. 74")
    assert not is_abrogated("parte della strada destinata allo scorrimento dei veicoli")


def test_cross_reference_definitions_are_detected() -> None:
    assert is_cross_reference("cfr.RAMO DI INTERSEZIONE.")
    assert is_cross_reference(" cfr. ISOLA DI CANALIZZAZIONE")
    assert not is_cross_reference("parte della strada (cfr. anche MARCIAPIEDE)")
