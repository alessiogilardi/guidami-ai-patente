"""ExplanationStatus's values must match the API's wire strings exactly (spec 0017, FR-6)."""

from guidami_ai_patente_bot.enums import ExplanationStatus


def test_the_members_match_the_apis_wire_strings() -> None:
    assert ExplanationStatus.CACHED == "cached"
    assert ExplanationStatus.UNCACHED == "uncached"
    assert ExplanationStatus.UNAVAILABLE == "unavailable"
