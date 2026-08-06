from domain.models.retrieval import RetrievedComma


def test_citation_includes_source() -> None:
    cds_comma = RetrievedComma(
        source="cds",
        article_number="43",
        article_title="Segnaletica",
        comma_number="3",
        text="Testo del comma.",
        distance=0.1,
    )
    reg_comma = RetrievedComma(
        source="reg",
        article_number="43",
        article_title="Segnaletica",
        comma_number="3",
        text="Altro testo.",
        distance=0.2,
    )

    assert cds_comma.citation != reg_comma.citation
    assert "cds" in cds_comma.citation
    assert "reg" in reg_comma.citation
