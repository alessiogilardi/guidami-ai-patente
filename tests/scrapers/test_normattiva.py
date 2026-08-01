import logging

import pytest

from scrapers.normattiva import ArticleRecord, _parse_article

_URL = "http://example"


def _commas(result: ArticleRecord) -> list[dict[str, str]]:
    """Read the `commas` field.

    `ArticleRecord` does not declare `commas` yet (T-1 adds it, replacing
    `paragraphs`) — indexing it directly trips the pyright hook's
    `reportGeneralTypeIssues` on every assertion. Centralizing the
    `type: ignore` here keeps the individual tests below reading exactly
    like the plan's failing-test spec (`result["commas"] == ...`).
    """
    return result["commas"]  # type: ignore[typeddict-item]


# --- T-1: comma extraction rewrite ------------------------------------------------


def test_parse_article_keeps_comma_with_no_text_span() -> None:
    """FR-2: a comma div with a number span but no `art_text_in_comma` span is kept."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 142</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">3.</span>
        Le seguenti categorie di veicoli...
      </div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result) == [{"number": "3", "text": "Le seguenti categorie di veicoli..."}]


def test_parse_article_structured_comma_number_not_in_text() -> None:
    """FR-1: the extracted number is stripped from the front of the comma's text."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 142</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">4-bis.</span>
        <span class="art_text_in_comma">L'utilizzo di un veicolo...</span>
      </div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result)[0] == {"number": "4-bis", "text": "L'utilizzo di un veicolo..."}


def test_parse_article_merges_unnumbered_list_items_into_preceding_comma() -> None:
    """FR-3: unnumbered list-item divs are merged into the preceding numbered comma."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 85</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">4-bis.</span>
        <span class="art_text_in_comma">prima parte</span>
      </div>
      <div class="art-comma-div-akn">a) alla prima violazione...</div>
      <div class="art-comma-div-akn">b) alla seconda violazione...</div>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert len(commas) == 1
    comma = commas[0]
    assert comma["number"] == "4-bis"
    idx_prima = comma["text"].index("prima parte")
    idx_a = comma["text"].index("a) alla prima violazione...")
    idx_b = comma["text"].index("b) alla seconda violazione...")
    assert idx_prima < idx_a < idx_b


def test_parse_article_discards_note_reference_only_divs() -> None:
    """FR-4: a div whose entire text is a note reference produces no comma."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 85</span>
      <div class="art-comma-div-akn">((190))</div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result) == []


def test_parse_article_logs_warning_for_leading_unnumbered_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """FR-3 AC3: an unnumbered block before any numbered comma is dropped with a warning."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 142</span>
      <div class="art-comma-div-akn">testo introduttivo senza numero</div>
    </div>
    """

    with caplog.at_level(logging.WARNING):
        result = _parse_article(html, _URL)

    assert _commas(result) == []
    assert any(
        "142" in record.getMessage() and "testo introduttivo senza numero" in record.getMessage()
        for record in caplog.records
    )


# --- T-2: title falls back to the unnumbered pre-comma block ----------------------


def test_parse_article_title_falls_back_to_pre_comma_block() -> None:
    """FR-5: an unnumbered pre-comma block becomes the title when the heading is absent."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 120</span>
      <div class="article-pre-comma-text-akn">
        Requisiti soggettivi per ottenere il rilascio della patente di guida...
      </div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert (
        result["title"]
        == "Requisiti soggettivi per ottenere il rilascio della patente di guida..."
    )


def test_parse_article_pre_comma_numbered_block_becomes_comma_not_title() -> None:
    """FR-5 AC2: a numbered pre-comma block is emitted as a comma, not used as the title."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 205</span>
      <div class="article-pre-comma-text-akn">((1. Contro l'ordinanza-ingiunzione...</div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result["title"] == ""
    assert _commas(result)[0] == {"number": "1", "text": "Contro l'ordinanza-ingiunzione..."}


def test_parse_article_heading_present_note_reference_pre_comma_ignored() -> None:
    """FR-5 AC3: a note-reference pre-comma block produces neither a title nor a comma."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 284</span>
      <span class="article-heading-akn">Sanzioni</span>
      <div class="article-pre-comma-text-akn">((70))</div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result["title"] == "Sanzioni"
    assert _commas(result) == []


# --- T-3: article-level repeal formula and art-just-text-akn container ------------


def test_parse_article_repealed_via_art_just_text_akn_formula() -> None:
    """FR-13: the article-repeal formula in `art-just-text-akn` flags the article repealed."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 127</span>
      <span class="art-just-text-akn">((ARTICOLO ABROGATO DAL D.P.R. 9 MARZO 2000, N. 104 ))</span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result["repealed"] is True
    assert _commas(result) == []


def test_parse_article_editorial_note_not_flagged_repealed() -> None:
    """FR-13: an "ABROGATO" substring outside `art-just-text-akn` no longer flags repeal."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 2</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">1.</span>
        <span class="art_text_in_comma">Ai fini del presente codice si intende...</span>
      </div>
      <div class="editorial-note">Nota: vedi anche NUMERO ABROGATO altrove.</div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result["repealed"] is False


def test_parse_article_art_just_text_akn_single_unnumbered_body_becomes_comma_one() -> None:
    """FR-14 AC1: an unnumbered `art-just-text-akn` body becomes a single comma numbered 1."""
    body_text = (
        "Il conducente e' tenuto ad osservare le prescrizioni tecniche di cui al presente "
        "articolo per l'intera durata del periodo transitorio previsto dalla normativa "
        "vigente in materia di sicurezza stradale e di omologazione dei veicoli a motore."
    )
    html = f"""
    <div class="article">
      <span class="article-num-akn">Art. 216</span>
      <span class="art-just-text-akn">{body_text}</span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result) == [{"number": "1", "text": body_text}]


def test_parse_article_art_just_text_akn_inline_numbered_comma() -> None:
    """FR-14 AC2: an inline numbered `art-just-text-akn` body is extracted per FR-1."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 121-octies</span>
      <span class="art-just-text-akn">
        ((1. l'IVASS e la CONSOB definiscono attraverso un protocollo d'intesa...
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result) == [
        {
            "number": "1",
            "text": "l'IVASS e la CONSOB definiscono attraverso un protocollo d'intesa...",
        }
    ]
