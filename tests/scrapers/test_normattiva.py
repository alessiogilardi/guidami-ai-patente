import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import scrapers.normattiva as normattiva
from scrapers.normattiva import (
    ArticleParams,
    ArticleRecord,
    LawConfig,
    _build_article_url,
    _extract_heading_title,
    _parse_article,
    _parse_toc,
    _process_article,
    _split_leading_title,
)

_URL = "http://example"


def _commas(result: ArticleRecord) -> list[dict[str, str]]:
    """Read the `commas` field."""
    return result.commas


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
        result.title == "Requisiti soggettivi per ottenere il rilascio della patente di guida..."
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

    assert result.title == ""
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

    assert result.title == "Sanzioni"
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

    assert result.repealed is True
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

    assert result.repealed is False


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


# --- T-1: REG law config (FR-1) ----------------------------------------------------


def test_reg_law_config_matches_urn_and_output_name() -> None:
    from scrapers.normattiva import BASE_URL, REG

    assert REG.slug == "reg"
    assert REG.output_name == "regolamento_attuazione.json"
    assert (
        REG.toc_url
        == BASE_URL
        + "/uri-res/N2Ls?urn:nir:stato:decreto.presidente.repubblica:1992-12-16;495!vig="
    )


# --- T-1: AMB law config (spec 0009 FR-1) ------------------------------------------


def test_amb_law_config_matches_urn_and_output_name() -> None:
    from scrapers.normattiva import AMB, BASE_URL

    assert AMB.slug == "amb"
    assert AMB.output_name == "codice_ambiente.json"
    assert (
        AMB.toc_url
        == BASE_URL + "/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2006-04-03;152!vig="
    )


def test_amb_registered_in_sources() -> None:
    from scrapers.normattiva import _SOURCES, AMB

    assert _SOURCES["amb"] is AMB


def test_parse_article_strips_full_word_articolo_prefix() -> None:
    """Regression test for the full-word "Articolo N" prefix.

    D.Lgs. 152/2006 uses "Articolo N" (full word) instead of "Art. N" for some
    articles (e.g. 177, 178-bis) — the number must still come out bare.
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Articolo 177</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">1.</span>
        Testo del comma.
      </div>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result.number == "177"


# --- T-2: leading `(Title)` split off the art-just-text-akn body (FR-2) -----------


def test_parse_article_title_split_from_leading_parenthesis() -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 116</span>
      <span class="art-just-text-akn">
        (Segnali di divieto generici) 1. I segnali di divieto relativi alla circolazione di
        tutti i veicoli sono elencati di seguito.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result.title == "Segnali di divieto generici"
    assert _commas(result)[0]["text"].startswith("I segnali di divieto")
    assert not result.title.startswith("(")
    assert not result.title.endswith(")")


def test_parse_article_no_leading_parenthesis_logs_warning_and_keeps_body_as_comma(
    caplog: pytest.LogCaptureFixture,
) -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 50</span>
      <span class="art-just-text-akn">1. Disposizione priva di titolo esplicito.</span>
    </div>
    """

    with caplog.at_level(logging.WARNING):
        result = _parse_article(html, _URL)

    assert result.title == ""
    assert _commas(result) == [{"number": "1", "text": "Disposizione priva di titolo esplicito."}]
    assert any("50" in record.getMessage() for record in caplog.records)


# --- T-3: segment art-just-text-akn into one comma per inline marker (FR-3) -------


def test_parse_article_just_text_akn_splits_multiple_inline_commas() -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 79</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Primo comma. 2. Secondo comma. 3. Terzo comma.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert _commas(result) == [
        {"number": "1", "text": "Primo comma."},
        {"number": "2", "text": "Secondo comma."},
        {"number": "3", "text": "Terzo comma."},
    ]


def test_parse_article_just_text_akn_leading_amendment_bracket_marker() -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 2</span>
      <span class="art-just-text-akn">
        ((1. Contro l'ordinanza-ingiunzione si puo' proporre opposizione. 2. L'opposizione e'
        presentata nel termine di trenta giorni.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert commas == [
        {"number": "1", "text": "Contro l'ordinanza-ingiunzione si puo' proporre opposizione."},
        {"number": "2", "text": "L'opposizione e' presentata nel termine di trenta giorni."},
    ]
    assert all("((" not in comma["text"] for comma in commas)


def test_parse_article_just_text_akn_ignores_false_positive_markers() -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 30</span>
      <span class="art-just-text-akn">
        1. Ai fini dell'art. 2. e del n. 495. si applica quanto disposto (fig. II.48) e la
        normativa del 16 dicembre 1992, n. 495. rimane invariata. 2. Il secondo comma
        disciplina altro.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2"]
    assert "art. 2." in commas[0]["text"]
    assert "n. 495." in commas[0]["text"]
    assert "16 dicembre 1992, n. 495." in commas[0]["text"]
    assert commas[1]["text"] == "Il secondo comma disciplina altro."


def test_parse_article_just_text_akn_noncontiguous_numbering_raises() -> None:
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 55</span>
      <span class="art-just-text-akn">1. Primo comma. 3. Terzo comma senza il secondo.</span>
    </div>
    """

    with pytest.raises(ValueError) as exc_info:
        _parse_article(html, _URL)

    assert "55" in str(exc_info.value)
    assert "['1', '3']" in str(exc_info.value)


# --- Regression tests: real-world patterns found via a live scrape ----------------
#
# The four cases below were not covered by the plan's original failing-test specs
# (T-2/T-3) because they were only discovered against real Normattiva pages during
# the actual `scrape-regolamento` run — the marker heuristic's initial version raised
# `ValueError` or produced wrong output on all four. Fixed directly in
# `_is_marker_start`/`_INLINE_MARKER_PATTERN`/`_extract_comma_number_and_text`/
# `_split_leading_title`/`_validate_contiguous_numbering`/`_parse_article`'s dedup
# step; these tests pin the fixed behavior against minimal reproductions.


def test_parse_article_just_text_akn_marker_after_closing_bracket() -> None:
    """A marker right after `))` (a preceding aside's close) is a genuine boundary.

    Real example: Regolamento art. 211 — "...M.C.T.C..)) 2. Nell'evenienza...".
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 211</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Le macchine operatrici possono circolare ((nonche' di quelle
        eventualmente riportate sulla carta di circolazione)) . 2. Nell'evenienza di cui
        al comma 1, possono altresi' circolare con attrezzature di lavoro.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2"]
    assert commas[1]["text"].startswith("Nell'evenienza")


def test_parse_article_just_text_akn_mid_body_amendment_bracket_inserts_commas() -> None:
    """`((N. ... M. ...))` mid-article (not just at the article's start) is recognised.

    Real example: Regolamento art. 4 — commas 4-6 inserted as a block: "... si provvede.
    ((4. I tratti ... 5. Successivamente ... 6. La consegna ...)) Qualora...".
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 4</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Primo comma. 2. Secondo comma. 3. Terzo comma. ((4. Comma quattro
        inserito per emendamento. 5. Comma cinque inserito per emendamento.)) 6. Comma
        sei originario.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2", "3", "4", "5", "6"]
    assert commas[3]["text"] == "Comma quattro inserito per emendamento."
    assert commas[5]["text"] == "Comma sei originario."


def test_parse_article_just_text_akn_marker_wrapped_with_no_space_before_close() -> None:
    """`((N.))` with no space before the closing bracket is still a recognised marker.

    The leftover `))` is stripped from the following comma's text — symmetric with
    the existing leading-`((` stripping. Real example: Regolamento art. 46's `((4.))`.
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 46</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Primo comma. 2. Secondo comma. 3. Terzo comma. ((4.)) Qualora
        l'accesso avvenga direttamente dalla strada, si applica quanto previsto.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2", "3", "4"]
    assert (
        commas[3]["text"]
        == "Qualora l'accesso avvenga direttamente dalla strada, si applica quanto previsto."
    )
    assert not commas[3]["text"].startswith(")")


def test_parse_article_just_text_akn_bis_suffixed_comma_does_not_raise() -> None:
    """A `-bis`-suffixed comma after its base number is a legitimate exception (AD-3).

    Not a contiguity failure — the CdS already has this convention; real example:
    Regolamento art. 9's `1, 2, 3, 3-bis`.
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 9</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Primo comma. 2. Secondo comma. 3. Terzo comma. 3-bis. Comma
        inserito dopo il terzo.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2", "3", "3-bis"]


def test_parse_article_just_text_akn_bis_suffix_out_of_place_still_raises() -> None:
    """A suffixed comma that does NOT immediately follow its base number still fails loudly."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 9</span>
      <span class="art-just-text-akn">1. Primo comma. 2. Secondo comma. 1-bis. Fuori posto.</span>
    </div>
    """

    with pytest.raises(ValueError, match="does not immediately follow"):
        _parse_article(html, _URL)


def test_parse_article_just_text_akn_repeated_comma_number_keeps_last_occurrence(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later amendment can re-emit an earlier comma's number to mark it repealed.

    Only the later occurrence is kept (Normattiva's "vigente" convention), with a
    warning, not silently — the DB's `UNIQUE (article_id, comma_number)` couldn't
    store both anyway. Real example: Regolamento art. 4's trailing
    `6. ((COMMA SOPPRESSO DAL D.P.R. ... N. 610))`.
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 4</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Primo comma. 2. Secondo comma originario. 2. ((COMMA SOPPRESSO DAL
        D.P.R. 16 SETTEMBRE 1996, N. 610)) .
      </span>
    </div>
    """

    with caplog.at_level(logging.WARNING):
        result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2"]
    assert "SOPPRESSO" in commas[1]["text"]
    assert any(
        "4" in record.getMessage() and "2" in record.getMessage() for record in caplog.records
    )


def test_parse_article_second_leading_parenthesis_kept_as_title() -> None:
    """Two consecutive leading `(...)` segments: the descriptive (last) one is the title.

    Real example: Regolamento art. 226 — "(Art. 70 Cod. Str.) (Servizio di piazza con
    veicoli a trazione animale) 1. ...".
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 226</span>
      <span class="art-just-text-akn">
        (Art. 70 Cod. Str.) (Servizio di piazza con veicoli a trazione animale) 1. I
        veicoli a trazione animale hanno le seguenti caratteristiche. 2. Il secondo
        comma disciplina altro.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    assert result.title == "Servizio di piazza con veicoli a trazione animale"
    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2"]
    assert commas[0]["text"].startswith("I veicoli a trazione animale")


# --- T-8: widen _is_marker_start's accepted preceding-punctuation set (FR-6) ------


def test_parse_article_recovers_article_83_comma_11() -> None:
    """FR-6/PD-8: a bare word with no punctuation before the marker is a boundary.

    Genuine comma boundary, provided it isn't glued to the marker. Real example:
    Regolamento art. 83 comma 10->11 — "...modello II.6/q2 11. Il modello II.7
    indica...". Comma 12, which follows a period as usual, pins that the fix
    doesn't merely shift the gap: without the fix, comma 11 merges into 10 and
    the numbering jumps straight from 10 to 12, which is what raised `ValueError`
    before this task.
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 83</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Comma uno. 2. Comma due. 3. Comma tre. 4. Comma quattro. 5.
        Comma cinque. 6. Comma sei. 7. Comma sette. 8. Comma otto. 9. Comma nove.
        10. I simboli da utilizzare per i pannelli integrativi modello II.6/q2 11.
        Il modello II.7 indica l'andamento della strada principale. 12. Nei
        pannelli integrativi e' vietato l'uso di iscrizioni.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == [str(n) for n in range(1, 13)]
    assert commas[9]["text"] == (
        "I simboli da utilizzare per i pannelli integrativi modello II.6/q2"
    )
    assert commas[10]["text"] == "Il modello II.7 indica l'andamento della strada principale."


def test_parse_article_recovers_article_194_comma_2() -> None:
    """FR-6/PD-8: a semicolon immediately before a marker is a genuine boundary.

    Same as the already-accepted closing `)`. Real example: Regolamento art. 194
    comma 1->2 — "...pulizia dei supporti; 2. Le imprese devono...".
    """
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 194</span>
      <span class="art-just-text-akn">
        (Titolo) 1. Le imprese devono disporre di attrezzature idonee per la
        pulizia dei supporti; 2. Le imprese devono altresi' disporre di
        attrezzature per la lavorazione meccanica dei supporti.
      </span>
    </div>
    """

    result = _parse_article(html, _URL)

    commas = _commas(result)
    assert [comma["number"] for comma in commas] == ["1", "2"]
    assert commas[0]["text"] == (
        "Le imprese devono disporre di attrezzature idonee per la pulizia dei supporti;"
    )
    assert commas[1]["text"] == (
        "Le imprese devono altresi' disporre di attrezzature per la lavorazione "
        "meccanica dei supporti."
    )


# --- T-1: LawConfig/ArticleParams/ArticleRecord become frozen dataclasses (FR-2) --


def test_law_config_missing_field_raises_at_construction() -> None:
    """AD-1: `LawConfig` is a frozen dataclass — omitting a required field raises."""
    with pytest.raises(TypeError):
        LawConfig(slug="x", toc_url="y")  # type: ignore[call-arg]


def test_article_record_asdict_matches_json_shape() -> None:
    """FR-2: `ArticleRecord` is a dataclass — `asdict` mirrors the persisted JSON shape."""
    html = """
    <div class="article">
      <span class="article-num-akn">Art. 1</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">1.</span>
        <span class="art_text_in_comma">Testo del comma.</span>
      </div>
    </div>
    """

    record = _parse_article(html, _URL)

    result = asdict(record)

    assert set(result.keys()) == {"number", "title", "commas", "url", "scraped_at", "repealed"}
    assert isinstance(result["commas"], list)
    assert all(set(comma.keys()) == {"number", "text"} for comma in result["commas"])


# --- T-4: `_parse_toc`/`_process_article`/`main` control-flow restructure (FR-1, FR-3, FR-4) --

_TEST_LAW = LawConfig(slug="test-law", toc_url="http://toc.example/toc", output_name="out.json")


def _toc_entry(id_articolo: str, id_sotto: str, flag: str = "0", progressivo: str = "1") -> str:
    """Builds one `caricaArticolo?...` onclick handler for a TOC HTML fixture."""
    qs = (
        f"art.versione=1&art.idGruppo=10&art.flagTipoArticolo={flag}"
        f"&art.codiceRedazionale=X&art.idArticolo={id_articolo}"
        f"&art.idSottoArticolo={id_sotto}&art.idSottoArticolo1=0"
        f"&art.dataPubblicazioneGazzetta=2020-01-01&art.progressivo={progressivo}"
    )
    return f'<a href="#" onclick="caricaArticolo?{qs}">Art. {id_articolo}</a>'


def _article_params(id_articolo: str = "5", id_sotto: str = "1") -> ArticleParams:
    return ArticleParams(
        versione="1",
        idGruppo="10",
        flagTipoArticolo="0",
        codiceRedazionale="X",
        idArticolo=id_articolo,
        idSottoArticolo=id_sotto,
        idSottoArticolo1="0",
        dataPubblicazioneGazzetta="2020-01-01",
        progressivo="1",
    )


def test_parse_toc_skips_non_article_flag_entries() -> None:
    """PD-4: only `flagTipoArticolo=0` entries are kept."""
    html = _toc_entry("1", "1", flag="0") + _toc_entry("2", "1", flag="1")

    result = _parse_toc(html)

    assert len(result) == 1
    assert result[0].idArticolo == "1"
    assert result[0].flagTipoArticolo == "0"


def test_parse_toc_deduplicates_repeated_article_sotto_pairs() -> None:
    """PD-4: a repeated `(idArticolo, idSottoArticolo)` pair is kept only once."""
    html = _toc_entry("3", "1", progressivo="1") + _toc_entry("3", "1", progressivo="2")

    result = _parse_toc(html)

    assert len(result) == 1


def test_process_article_records_fetch_failed_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(normattiva.time, "sleep", lambda *_: None)
    params = _article_params()
    client = MagicMock()
    client.get.return_value = httpx.Response(500, text="")
    manifest = MagicMock()

    result = _process_article(params, _TEST_LAW, _TEST_LAW.toc_url, tmp_path, client, manifest)

    assert result is None
    expected_url = _build_article_url(params)
    manifest.record_skip.assert_called_once_with("fetch_failed", "Art. 5", expected_url)


def test_process_article_records_session_invalid_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(normattiva.time, "sleep", lambda *_: None)
    params = _article_params()
    client = MagicMock()
    client.get.return_value = httpx.Response(200, text="<html>no marker here</html>")
    manifest = MagicMock()

    result = _process_article(params, _TEST_LAW, _TEST_LAW.toc_url, tmp_path, client, manifest)

    assert result is None
    expected_url = _build_article_url(params)
    manifest.record_skip.assert_called_once_with("session_invalid", "Art. 5", expected_url)


def test_process_article_records_parse_error_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(normattiva.time, "sleep", lambda *_: None)
    params = _article_params(id_articolo="55")
    article_html = """
    <div class="article">
      <span class="article-num-akn">Art. 55</span>
      <span class="art-just-text-akn">1. Primo comma. 3. Terzo comma senza il secondo.</span>
    </div>
    """
    client = MagicMock()
    client.get.return_value = httpx.Response(200, text=article_html)
    manifest = MagicMock()

    result = _process_article(params, _TEST_LAW, _TEST_LAW.toc_url, tmp_path, client, manifest)

    assert result is None
    manifest.record_skip.assert_called_once()
    category, label, detail = manifest.record_skip.call_args[0]
    assert category == "parse_error"
    assert label == "Art. 55"
    assert "55" in detail


def test_process_article_returns_record_on_success_and_records_no_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(normattiva.time, "sleep", lambda *_: None)
    params = _article_params()
    article_html = """
    <div class="article">
      <span class="article-num-akn">Art. 5</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">1.</span>
        <span class="art_text_in_comma">Testo del comma.</span>
      </div>
    </div>
    """
    client = MagicMock()
    client.get.return_value = httpx.Response(200, text=article_html)
    manifest = MagicMock()

    result = _process_article(params, _TEST_LAW, _TEST_LAW.toc_url, tmp_path, client, manifest)

    assert result is not None
    assert result.number == "5"
    assert result.title == ""
    manifest.record_skip.assert_not_called()


def test_main_clean_run_writes_output_and_finalizes_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(normattiva.time, "sleep", lambda *_: None)

    law = LawConfig(slug="test-law", toc_url="http://toc.example/toc", output_name="out.json")
    toc_html = _toc_entry("1", "1")
    article_html = """
    <div class="article">
      <span class="article-num-akn">Art. 1</span>
      <div class="art-comma-div-akn">
        <span class="comma-num-akn">1.</span>
        <span class="art_text_in_comma">Testo del comma.</span>
      </div>
    </div>
    """

    def fake_get(url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url == law.toc_url:
            return httpx.Response(200, text=toc_html, request=request)
        return httpx.Response(200, text=article_html, request=request)

    mock_client = MagicMock()
    mock_client.get.side_effect = fake_get
    mock_client_cm = MagicMock()
    mock_client_cm.__enter__.return_value = mock_client
    mock_client_cm.__exit__.return_value = False
    monkeypatch.setattr(normattiva.httpx, "Client", MagicMock(return_value=mock_client_cm))

    data_root = tmp_path / "data"
    logs_root = tmp_path / "logs"

    normattiva.main(law, data_root=data_root, logs_root=logs_root)

    output_path = data_root / "parsed" / law.slug / law.output_name
    assert output_path.exists()
    records = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["number"] == "1"

    run_dirs = list(logs_root.iterdir())
    assert len(run_dirs) == 1
    assert run_dirs[0].name.startswith(f"scrape_{law.slug}_")

    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["found"] == 1
    assert manifest["saved"] == 1
    assert manifest["skipped"] == {"fetch_failed": 0, "session_invalid": 0, "parse_error": 0}

    report = (run_dirs[0] / "report.md").read_text(encoding="utf-8")
    assert report.count("None") == 3


def test_main_dry_run_makes_no_http_request_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _fail_if_constructed(*args: object, **kwargs: object) -> None:
        pytest.fail("httpx.Client should not be constructed during a dry run")

    monkeypatch.setattr(normattiva.httpx, "Client", _fail_if_constructed)

    law = LawConfig(slug="test-law", toc_url="http://toc.example/toc", output_name="out.json")
    data_root = tmp_path / "data"
    logs_root = tmp_path / "logs"

    normattiva.main(law, dry_run=True, data_root=data_root, logs_root=logs_root)

    assert not data_root.exists()
    assert not logs_root.exists()


# --- T-5: `scrape` CLI entry point, replacing main_cds/main_cap/main_reg (FR-1, AD-2) --


def test_cli_main_dispatches_to_main_with_resolved_source(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_main = MagicMock()
    monkeypatch.setattr(normattiva, "main", mock_main)
    monkeypatch.setattr(sys, "argv", ["scrape", "--source", "reg"])

    normattiva.cli_main()

    mock_main.assert_called_once_with(normattiva.REG, dry_run=False)


def test_cli_main_dry_run_flag_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_main = MagicMock()
    monkeypatch.setattr(normattiva, "main", mock_main)
    monkeypatch.setattr(sys, "argv", ["scrape", "--source", "cds", "--dry-run"])

    normattiva.cli_main()

    mock_main.assert_called_once_with(normattiva.CDS, dry_run=True)


def test_build_parser_rejects_unknown_source() -> None:
    with pytest.raises(SystemExit):
        normattiva._build_parser().parse_args(["--source", "bogus"])


# --- T-7: bracket-aware title extraction (FR-5) ------------------------------------


def test_split_leading_title_strips_leading_amendment_bracket() -> None:
    """PD-7: a leading `((` amendment bracket no longer blocks title extraction.

    Real example: Regolamento art. 6's raw `art-just-text-akn` body.
    """
    body_text = (
        "(( (Modalità e procedura per l'esercizio della diffida). 1. Il potere di diffida..."
    )

    title, remaining = _split_leading_title(body_text, "6")

    assert title == "Modalità e procedura per l'esercizio della diffida"
    assert remaining == ". 1. Il potere di diffida..."


def test_extract_heading_title_common_unwrapped_case_unchanged() -> None:
    """FR-5: a heading with no leading parenthesis at all is returned unchanged."""
    raw = "Definizione e classificazione delle strade"

    assert _extract_heading_title(raw) == raw


def test_extract_heading_title_well_formed_single_wrap_unchanged() -> None:
    """FR-5: a well-formed single `(Title)` wrap still strips the parens."""
    raw = "(Segnaletica orizzontale)"

    assert _extract_heading_title(raw) == "Segnaletica orizzontale"


def test_extract_heading_title_double_bracket_with_trailing_debris() -> None:
    """PD-7: a `((` wrap with trailing `))` debris no longer leaks into the title.

    Real example: CdS art. 9-bis's raw `article-heading-akn` text.
    """
    raw = (
        "(( (Organizzazione di competizioni non autorizzate in velocità con veicoli "
        "a motore e partecipazione alle gare). ))"
    )

    result = _extract_heading_title(raw)

    assert result == (
        "Organizzazione di competizioni non autorizzate in velocità con veicoli a "
        "motore e partecipazione alle gare"
    )
    assert not result.startswith(" ")
    assert not result.endswith(")")
    assert not result.endswith(". ")


def test_extract_heading_title_double_bracket_no_space_before_close() -> None:
    """PD-7: a `((` wrap with no space before the closing `)` is parsed correctly.

    Real example: CAP art. 3's raw `article-heading-akn` text.
    """
    raw = "(( (Finalità della vigilanza).))"

    assert _extract_heading_title(raw) == "Finalità della vigilanza"


def test_extract_heading_title_glued_cross_reference_note_discarded() -> None:
    """PD-7: a cross-reference note glued (no separating space) to the title is discarded.

    Real example: Regolamento art. 16's raw `article-heading-akn` text.
    """
    raw = "(Art. 10 Cod. Str.)Provvedimento di autorizzazione"

    assert _extract_heading_title(raw) == "Provvedimento di autorizzazione"


def test_extract_heading_title_multi_segment_keeps_last() -> None:
    """PD-7: consecutive leading `(...)` segments keep the last (descriptive) one."""
    raw = "(Art. 70 Cod. Str.) (Servizio di piazza con veicoli a trazione animale)"

    assert _extract_heading_title(raw) == "Servizio di piazza con veicoli a trazione animale"
