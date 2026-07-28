from commons.utils import element_id


def test_is_deterministic() -> None:
    assert element_id("cds", "2") == element_id("cds", "2")


def test_parts_disambiguate() -> None:
    assert element_id("cds", "2") != element_id("cap", "2")


def test_matches_expected_uuid5() -> None:
    """Golden value: regression guard on namespace/algorithm (Decision 1 & Risks)."""
    assert element_id("cds", "2") == "72b96ca3-95b7-53a5-bb7c-a1917d6bd1cd"
