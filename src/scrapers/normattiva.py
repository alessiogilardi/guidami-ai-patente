"""Scraper for normattiva.it — supports multiple Italian laws."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from bs4.element import PageElement

from commons.observability import LOG_FORMAT, RunArtifactWriter, RunArtifactWriterConfig

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.normattiva.it"
ARTICLE_URL = BASE_URL + "/atto/caricaArticolo"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_BASE_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9",
}

DELAY_SECONDS = 1.5
MAX_RETRIES = 3


@dataclass(frozen=True)
class LawConfig:
    """Configuration for scraping a legal text from normattiva.it."""

    slug: str  # used for directory and file naming
    toc_url: str  # normattiva.it URN URL with !vig=
    output_name: str  # output JSON filename


CDS = LawConfig(
    slug="cds",
    toc_url=BASE_URL + "/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:1992-04-30;285!vig=",
    output_name="codice_della_strada.json",
)

CAP = LawConfig(
    slug="cap",
    toc_url=BASE_URL + "/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2005-09-07;209!vig=",
    output_name="codice_assicurazioni_private.json",
)

REG = LawConfig(
    slug="reg",
    toc_url=BASE_URL
    + "/uri-res/N2Ls?urn:nir:stato:decreto.presidente.repubblica:1992-12-16;495!vig=",
    output_name="regolamento_attuazione.json",
)


@dataclass(frozen=True)
class ArticleParams:
    """Query parameters for the call to normattiva.it's caricaArticolo API."""

    versione: str
    idGruppo: str
    flagTipoArticolo: str
    codiceRedazionale: str
    idArticolo: str
    idSottoArticolo: str
    idSottoArticolo1: str
    dataPubblicazioneGazzetta: str
    progressivo: str


@dataclass(frozen=True)
class ArticleRecord:
    """Record of a legal article extracted and serialized to JSON."""

    number: str
    title: str
    commas: list[dict[str, str]]  # each item: {"number": str, "text": str}
    url: str
    scraped_at: str
    repealed: bool  # abrogato


_COMMA_NUMBER_PATTERN = re.compile(r"^(\d+(?:-[a-z]+)?)\.?\s*")
_INLINE_MARKER_PATTERN = re.compile(r"(\d+(?:-[a-z]+)?)\.(?:\s|\))")
_MARKER_FALSE_POSITIVE_PREFIXES = frozenset({"art", "artt", "n", "nn", "fig"})


def _extract_comma_number_and_text(raw_text: str) -> tuple[str, str] | None:
    """Extract a comma's legal number and text from `raw_text`.

    The number is recognised by shape — one or more digits optionally followed by
    `-` and a lowercase word — never validated against a whitelist of suffixes
    (FR-1 AC4).

    Returns:
        `(number, text)` when a number is found at the start of `raw_text`, with the
        number (and, if present, a leading `((` marker and the following `.` and
        whitespace) stripped from the front of `text`.
        `("", text)` when no number is found and the block is not discardable —
        the caller merges it into the preceding comma (FR-3).
        `None` when the text, after removing all `((`/`))` occurrences and
        surrounding whitespace, is empty or consists only of digits — a note
        reference or bare marker fragment (FR-4).
    """
    text = raw_text.strip()
    marker_free = text.replace("((", "").replace("))", "").strip()
    if not marker_free or re.fullmatch(r"\d+", marker_free):
        return None

    matchable = text[2:].lstrip() if text.startswith("((") else text
    match = _COMMA_NUMBER_PATTERN.match(matchable)
    if match:
        number = match.group(1)
        comma_text = matchable[match.end() :].strip()
        # A `((N.))` amendment marker (number wrapped on both sides, no space before
        # the closing bracket) leaves a leading `))` on the text; strip it, symmetric
        # with the leading `((` already stripped above.
        if comma_text.startswith("))"):
            comma_text = comma_text[2:].lstrip()
        return number, comma_text

    return "", text


def _split_leading_title(body_text: str, article_number: str) -> tuple[str, str]:
    """Splits the leading `(Title)` segment(s) off `body_text` (FR-2).

    A title segment is a single-parenthesis segment — `(...)`, not the `((`
    amendment-bracket marker — at the very start of `body_text`. Some
    articles carry a leading cross-reference note before the real title
    (e.g. `(Art. 70 Cod. Str.) (Servizio di piazza...)`); every consecutive
    leading `(...)` segment is stripped, and the *last* one stripped is kept
    as the title, since it is the descriptive one. A leading `((`
    amendment-bracket marker is stripped first, so a title wrapped in it
    (e.g. `(( (Title). 1. ...`) is still found. Returns
    `(title, remaining_text)`. If no leading title segment is found at all
    (no leading `(`, a leading `((`, or no closing `)`), returns
    `("", body_text)` unchanged and logs a `warning` naming `article_number`.
    """
    remaining = body_text.lstrip()
    if remaining.startswith("(("):
        remaining = remaining[2:].lstrip()
    title = ""
    found = False
    while remaining.startswith("(") and not remaining.startswith("(("):
        end = remaining.find(")")
        if end == -1:
            break
        title = remaining[1:end].strip()
        remaining = remaining[end + 1 :].lstrip()
        found = True
    if not found:
        logger.warning(
            "Article %s: art-just-text-akn body has no leading title parenthesis",
            article_number,
        )
        return "", body_text
    return title, remaining


def _extract_heading_title(raw_heading: str) -> str:
    """Extracts the title from `article-heading-akn`'s raw text (FR-5).

    Strips a leading `((` amendment-bracket marker first, then extracts the leading
    `(...)` segment(s): every segment not glued (no separating space/punctuation) to
    more text is stripped, keeping the *last* one as the title (mirrors
    `_split_leading_title`'s multi-segment handling); a segment immediately followed
    by an alphanumeric character is instead a glued cross-reference note (e.g.
    `(Art. 10 Cod. Str.)Provvedimento di autorizzazione`), discarded in favor of the
    text that follows it. Text with no leading `(` at all (the common case) is
    returned unchanged, edge-trimmed of stray `().` and whitespace — e.g. a bare
    `(( Title ))` (no inner single-paren wrap) leaves a trailing space once the
    `))` is stripped, since `strip` only removes the characters given it.
    """
    remaining = raw_heading.strip()
    if remaining.startswith("(("):
        remaining = remaining[2:].lstrip()
    if not remaining.startswith("("):
        return remaining.strip("(). ")
    title = remaining
    while remaining.startswith("(") and not remaining.startswith("(("):
        end = remaining.find(")")
        if end == -1:
            break
        segment = remaining[1:end].strip()
        rest = remaining[end + 1 :]
        if rest[:1].isalnum():
            return rest.strip()
        title = segment
        remaining = rest.lstrip()
    return title


def _preceding_word(text: str, index: int) -> str:
    """Returns the lowercase word immediately ending at `text[:index]`, or `""`."""
    match = re.search(r"([A-Za-zàèéìòù]+)$", text[:index])
    return match.group(1).lower() if match else ""


def _is_marker_start(text: str, start: int) -> bool:
    """True if `start` is a genuine inline comma-number marker start (FR-3 AC1-AC3).

    A position qualifies when:
    - it is the very start of `text`, or only `(`/whitespace precedes it (a
      leading `((` amendment bracket at the very start of the article);
    - it is immediately preceded by `((` (an amendment bracket opening
      elsewhere in the article, not only at its start — real Regolamento
      articles insert whole later commas this way, e.g. `... si provvede.
      ((4. I tratti ...`);
    - the nearest non-whitespace character before it is `)` or `;` (the close
      of a preceding parenthetical aside or amendment bracket, e.g.
      `...M.C.T.C..)) 2. Nell'evenienza...`, or a semicolon-terminated
      sub-list item, e.g. `...pulizia dei supporti; 2. Le imprese...`) —
      always a genuine boundary;
    - the nearest non-whitespace character before it is `.` and the word
      immediately before that period is not one of
      `_MARKER_FALSE_POSITIVE_PREFIXES` (abbreviations such as "art.", "n.",
      "fig." that also end in digit+period but do not start a new comma);
    - there is no `.`/`)`/`;` immediately before it at all, but the token
      immediately preceding it itself ends in a digit — a deliberately
      narrow signal for an alphanumeric code/reference immediately preceding
      the marker (e.g. `...modello II.6/q2 11. Il modello II.7...`), not a
      general "any bare token is a boundary" rule. FR-6's original broader
      formulation (any non-whitespace, non-glued token as a boundary) was
      found to cause 51 new false-positive comma splits across the
      Regolamento corpus during verification — ordinary numeric
      cross-references in prose (`...commi 4, 5 e 6. La decorrenza...`,
      `...all'articolo 266. ((46))...`, bare years like `...finanziario
      1994. 3. Per il...`) are indistinguishable from a genuine marker under
      that rule. Generalizing this narrow digit-ending heuristic into a
      safer, broader rule is deferred to a future enhancement — this scope
      is deliberately limited to the two verified real cases (Regolamento
      art. 83 comma 11, art. 194 comma 2).
    """
    if start == 0 or not text[:start].strip("( "):
        return True
    if start >= 2 and text[start - 2 : start] == "((":
        return True
    match = re.search(r"([.)\;])\s+$", text[:start])
    if match is None:
        return bool(re.search(r"\d\s+$", text[:start]))
    if match.group(1) in (")", ";"):
        return True
    return _preceding_word(text, match.start()) not in _MARKER_FALSE_POSITIVE_PREFIXES


def _split_into_comma_segments(text: str) -> list[str]:
    """Splits `text` into one segment per recognised inline comma marker (FR-3).

    Returns `[text]` unchanged if no marker is found.
    """
    starts = [
        match.start()
        for match in _INLINE_MARKER_PATTERN.finditer(text)
        if _is_marker_start(text, match.start())
    ]
    if not starts:
        return [text]
    boundaries = [*starts, len(text)]
    return [text[boundaries[i] : boundaries[i + 1]] for i in range(len(starts))]


def _validate_contiguous_numbering(numbers: list[str], article_number: str) -> None:
    """Raises `ValueError` unless `numbers` is base-contiguous, allowing suffixes.

    Allows `-bis`/`-ter`-style suffixes immediately after their base number
    (AD-3's relaxed rule: real Regolamento articles do insert a suffixed comma,
    e.g. art. 9's `1, 2, 3, 3-bis`, the same convention the CdS uses — the base
    sequence must still be strictly contiguous with no gap/duplicate, which is
    what actually catches a mis-segmentation).
    """
    if not numbers:
        return
    base_sequence = [number for number in numbers if "-" not in number]
    expected_bases = [str(i) for i in range(1, len(base_sequence) + 1)]
    if base_sequence != expected_bases:
        raise ValueError(
            f"Article {article_number}: comma base numbers are not contiguous from 1: {numbers}"
        )
    last_base_seen: str | None = None
    for number in numbers:
        base = number.split("-", 1)[0]
        if "-" in number and base != last_base_seen:
            raise ValueError(
                f"Article {article_number}: suffixed comma {number!r} does not "
                f"immediately follow its base number {last_base_seen!r}: {numbers}"
            )
        last_base_seen = base


def _sotto_articolo_suffix(sotto: str) -> str:
    suffixes = {"1": "", "2": " bis", "3": " ter", "4": " quater", "5": " quinquies"}
    return suffixes.get(sotto, f" ({sotto})")


def _parse_toc(html: str) -> list[ArticleParams]:
    """Extract unique article parameters from the TOC page onclick handlers."""
    pattern = re.compile(r"caricaArticolo\?([^'\"]+)")
    seen: set[tuple[str, str]] = set()
    results: list[ArticleParams] = []

    for match in pattern.finditer(html):
        raw_qs = match.group(1).rstrip("&")
        qs = parse_qs(raw_qs, keep_blank_values=True)

        def get(key: str) -> str:
            vals = qs.get(f"art.{key}", qs.get(key, [""]))
            return vals[0].strip() if vals else ""

        flag = get("flagTipoArticolo")
        id_art = get("idArticolo")
        id_sotto = get("idSottoArticolo")
        key = (id_art, id_sotto)
        if flag == "0" and key not in seen:
            seen.add(key)
            results.append(
                ArticleParams(
                    versione=get("versione"),
                    idGruppo=get("idGruppo"),
                    flagTipoArticolo=flag,
                    codiceRedazionale=get("codiceRedazionale"),
                    idArticolo=id_art,
                    idSottoArticolo=id_sotto,
                    idSottoArticolo1=get("idSottoArticolo1"),
                    dataPubblicazioneGazzetta=get("dataPubblicazioneGazzetta"),
                    progressivo=get("progressivo") or "0",
                )
            )

    results.sort(key=lambda p: (int(p.idArticolo), int(p.idSottoArticolo)))
    return results


def _build_article_url(params: ArticleParams) -> str:
    qs = {
        "art.versione": params.versione,
        "art.idGruppo": params.idGruppo,
        "art.flagTipoArticolo": params.flagTipoArticolo,
        "art.codiceRedazionale": params.codiceRedazionale,
        "art.idArticolo": params.idArticolo,
        "art.idSottoArticolo": params.idSottoArticolo,
        "art.idSottoArticolo1": params.idSottoArticolo1,
        "art.dataPubblicazioneGazzetta": params.dataPubblicazioneGazzetta,
        "art.progressivo": params.progressivo,
    }
    return f"{ARTICLE_URL}?{urlencode(qs)}"


def _extract_numero_and_titolo(soup: BeautifulSoup) -> tuple[str, str]:
    """Extracts the article number and heading title.

    Reads `article-num-akn`/`article-heading-akn`.
    """
    num_tag = soup.find(class_="article-num-akn")
    numero_raw = num_tag.get_text(strip=True) if num_tag else ""
    numero = re.sub(r"^Art\.\s*", "", numero_raw)

    heading_tag = soup.find(class_="article-heading-akn")
    titolo = _extract_heading_title(heading_tag.get_text(strip=True)) if heading_tag else ""
    return numero, titolo


def _build_commi_from_comma_divs(soup: BeautifulSoup, numero: str) -> list[dict[str, str]]:
    """Builds the structured `commi` list from `art-comma-div-akn` elements.

    FR-1/FR-2/FR-3/FR-4: structured comma numbers, list bodies kept, list items
    merged into the comma that introduces them, note fragments discarded.
    """
    commi: list[dict[str, str]] = []
    for comma_div in soup.find_all(class_="art-comma-div-akn"):
        num_span = comma_div.find(class_="comma-num-akn")
        text_span = comma_div.find(class_="art_text_in_comma")
        if text_span is not None:
            prefix = num_span.get_text(strip=True) + " " if num_span is not None else ""
            raw_text = prefix + text_span.get_text(separator=" ", strip=True)
        else:
            raw_text = comma_div.get_text(separator=" ", strip=True)

        result = _extract_comma_number_and_text(raw_text)
        if result is not None:
            number, comma_text = result
            if number:
                commi.append({"number": number, "text": comma_text})
            elif commi:
                commi[-1]["text"] = f"{commi[-1]['text']} {comma_text}"
            else:
                logger.warning(
                    "Discarding unnumbered pre-comma block in article %s: %s",
                    numero,
                    comma_text[:80],
                )
    return commi


def _apply_pre_comma_block(soup: BeautifulSoup, commi: list[dict[str, str]], titolo: str) -> str:
    """Handles the `article-pre-comma-text-akn` block against `commi` and `titolo`.

    `commi` is mutated in place. FR-5: a missing title falls back to the unnumbered
    pre-comma block; a numbered pre-comma block is a comma, not a title (prepended
    so it stays first). Returns the (possibly updated) title.
    """
    pre_comma_tag = soup.find(class_="article-pre-comma-text-akn")
    if pre_comma_tag is not None:
        pre_comma_result = _extract_comma_number_and_text(
            pre_comma_tag.get_text(separator=" ", strip=True)
        )
        if pre_comma_result is not None:
            pre_comma_number, pre_comma_text = pre_comma_result
            if pre_comma_number:
                commi.insert(0, {"number": pre_comma_number, "text": pre_comma_text})
            elif not titolo:
                titolo = pre_comma_text.strip()
    return titolo


def _detect_article_repeal(just_text_tag: PageElement | None) -> tuple[str, bool]:
    """Anchors article-level repeal detection to `art-just-text-akn`'s repeal formula.

    FR-13: not to a substring match anywhere in the page. `just_text_tag` is the
    (possibly `None`) `art-just-text-akn` element. Returns `(just_raw_text,
    abrogato)` — the tag's normalized raw text (empty when the tag is absent) and
    whether it opens with the repeal formula.
    """
    if just_text_tag is not None:
        just_raw_text = just_text_tag.get_text(separator=" ", strip=True)
        just_raw_text = re.sub(r"\s+", " ", just_raw_text)
        normalized_repeal_text = just_raw_text
        if normalized_repeal_text.startswith("(("):
            normalized_repeal_text = normalized_repeal_text[2:].lstrip()
        if normalized_repeal_text.endswith("))"):
            normalized_repeal_text = normalized_repeal_text[:-2].rstrip()
        abrogato = normalized_repeal_text.upper().startswith("ARTICOLO ABROGATO")
    else:
        just_raw_text = ""
        abrogato = False
    return just_raw_text, abrogato


def _apply_just_text_akn_body(
    commi: list[dict[str, str]], titolo: str, just_raw_text: str, numero: str
) -> str:
    """Splits `art-just-text-akn`'s body into commas, when it isn't a repeal formula.

    FR-14: `art-just-text-akn` is a fourth body container, subject to the same
    rules as the other comma sources. `commi` is mutated in place. Handles the
    leading-title split, inline comma segmentation, numbering, dedup-keep-last, and
    contiguous-numbering validation. Returns the (possibly updated) title.
    """
    body_text = just_raw_text
    if not titolo:
        titolo, body_text = _split_leading_title(body_text, numero)
    just_text_start = len(commi)
    for segment in _split_into_comma_segments(body_text):
        just_text_result = _extract_comma_number_and_text(segment)
        if just_text_result is not None:
            just_number, just_comma_text = just_text_result
            if just_number:
                commi.append({"number": just_number, "text": just_comma_text})
            elif commi:
                commi[-1]["text"] = f"{commi[-1]['text']} {just_comma_text}"
            else:
                commi.append({"number": "1", "text": just_comma_text})
    # A later amendment can re-emit a comma number to mark it repealed/replaced
    # (e.g. `((COMMA SOPPRESSO ...))` reusing an earlier comma's number) — keep
    # only the last occurrence, matching Normattiva's "vigente" (currently in
    # force) convention; `dict` preserves the number's *first* position while
    # keeping its *last* text, so the replacement lands where that comma belongs.
    deduped: dict[str, dict[str, str]] = {}
    for comma in commi[just_text_start:]:
        if comma["number"] in deduped:
            logger.warning(
                "Article %s: comma %s repeated in art-just-text-akn body, "
                "keeping the later occurrence",
                numero,
                comma["number"],
            )
        deduped[comma["number"]] = comma
    commi[just_text_start:] = list(deduped.values())
    _validate_contiguous_numbering(list(deduped.keys()), numero)
    return titolo


def _parse_article(html: str, url: str) -> ArticleRecord:
    """Extract structured data from an article's HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    numero, titolo = _extract_numero_and_titolo(soup)
    commi = _build_commi_from_comma_divs(soup, numero)
    titolo = _apply_pre_comma_block(soup, commi, titolo)

    just_text_tag = soup.find(class_="art-just-text-akn")
    just_raw_text, abrogato = _detect_article_repeal(just_text_tag)
    if just_text_tag is not None and not abrogato:
        titolo = _apply_just_text_akn_body(commi, titolo, just_raw_text, numero)

    return ArticleRecord(
        number=numero,
        title=titolo,
        commas=commi,
        url=url,
        scraped_at=datetime.now(UTC).isoformat(),
        repealed=abrogato,
    )


def _headers(toc_url: str) -> dict[str, str]:
    return {**_BASE_HEADERS, "Referer": toc_url}


def _refresh_session(client: httpx.Client, toc_url: str) -> None:
    with contextlib.suppress(httpx.RequestError):
        client.get(toc_url, headers=_headers(toc_url))


def _fetch_with_retry(
    client: httpx.Client,
    url: str,
    toc_url: str,
) -> httpx.Response | None:
    headers = _headers(toc_url)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 503):
                # Normattiva returns 500 as rate limiting — refresh session and wait
                print(f"\n  HTTP {resp.status_code}, refreshing session and waiting…")
                _refresh_session(client, toc_url)
                wait = 15 * attempt
                time.sleep(wait)
            else:
                print(f"\n  HTTP {resp.status_code} on attempt {attempt}")
                if attempt == MAX_RETRIES:
                    return None
                time.sleep(DELAY_SECONDS * attempt)
        except httpx.RequestError as exc:
            print(f"\n  Request error on attempt {attempt}: {exc}")
            if attempt == MAX_RETRIES:
                return None
            time.sleep(DELAY_SECONDS * attempt)
    return None


def _process_article(
    params: ArticleParams,
    law: LawConfig,
    toc_url: str,
    raw_dir: Path,
    client: httpx.Client,
    writer: RunArtifactWriter,
) -> ArticleRecord | None:
    """Fetches, saves and parses one article.

    Returns the parsed `ArticleRecord`, or `None` after recording a skip on
    `writer` (fetch failure, session invalid after refresh, or parse error).
    """
    suffix = _sotto_articolo_suffix(params.idSottoArticolo)
    label = f"Art. {params.idArticolo}{suffix}"
    url = _build_article_url(params)
    raw_filename = f"art_{int(params.idArticolo):04d}_{params.idSottoArticolo}.html"
    logger.debug("Fetching %s", label)

    resp = _fetch_with_retry(client, url, toc_url)
    if resp is None:
        writer.record_skip("fetch_failed", label, url)
        logger.warning("Skipping %s: fetch failed after retries", label)
        return None

    raw_html = resp.text
    if "article-num-akn" not in raw_html:
        logger.warning("Session invalid for %s, refreshing", label)
        _refresh_session(client, toc_url)
        time.sleep(5)
        resp = _fetch_with_retry(client, url, toc_url)
        if resp is None or "article-num-akn" not in resp.text:
            writer.record_skip("session_invalid", label, url)
            logger.warning("Skipping %s: still invalid after session refresh", label)
            return None
        raw_html = resp.text

    (raw_dir / raw_filename).write_text(raw_html, encoding="utf-8")

    try:
        record = _parse_article(raw_html, url)
    except ValueError as exc:
        writer.record_skip("parse_error", label, str(exc))
        logger.warning("Skipping %s: parse error: %s", label, exc)
        return None

    logger.debug("Parsed %s: %s", label, record.title or "(untitled)")
    return record


def main(
    law: LawConfig,
    *,
    dry_run: bool = False,
    data_root: Path = Path("data"),
    logs_root: Path = Path("logs"),
) -> None:
    """Download the legal text specified by `law` and save it to `data_root/parsed/`.

    When `dry_run` is True, prints the TOC URL and the output path that would be used
    and returns without performing any HTTP request or filesystem write.
    """
    raw_dir = data_root / "raw" / law.slug
    processed_dir = data_root / "parsed" / law.slug
    output_path = processed_dir / law.output_name

    if dry_run:
        print(f"Would fetch TOC from {law.toc_url}")
        print(f"Would write raw HTML under {raw_dir}/ and parsed JSON to {output_path}")
        return

    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    toc_url = law.toc_url
    headers = _headers(toc_url)

    writer_config = RunArtifactWriterConfig(
        logs_root=logs_root, source=law.slug, toc_url=toc_url, output_path=output_path
    )
    with RunArtifactWriter(writer_config) as writer:
        logger.info("Logging to %s", writer.log_file)
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            logger.info("Fetching TOC for %s", law.slug)
            toc_resp = client.get(toc_url, headers=headers)
            toc_resp.raise_for_status()

            toc_html = toc_resp.text
            (raw_dir / "toc.html").write_text(toc_html, encoding="utf-8")

            articles_params = _parse_toc(toc_html)
            writer.set_found(len(articles_params))
            logger.info("Found %d articles in TOC", len(articles_params))

            records: list[ArticleRecord] = []
            for i, params in enumerate(articles_params, start=1):
                logger.debug("[%d/%d] Art. %s", i, len(articles_params), params.idArticolo)
                record = _process_article(params, law, toc_url, raw_dir, client, writer)
                if record is not None:
                    records.append(record)
                    writer.record_saved()
                time.sleep(DELAY_SECONDS)

            output_path.write_text(
                json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("Done: %d articles saved to %s", len(records), output_path)


_SOURCES: dict[str, LawConfig] = {"cds": CDS, "cap": CAP, "reg": REG}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrape", description="Scrape a normattiva.it legal text."
    )
    parser.add_argument("--source", required=True, choices=sorted(_SOURCES), help="Law to scrape.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be fetched/written and exit; no HTTP request, no filesystem write.",
    )
    return parser


def cli_main() -> None:
    """Entry point registered as `scrape` in `[project.scripts]`."""
    args = _build_parser().parse_args()
    if not args.dry_run:
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, force=True)
    main(_SOURCES[args.source], dry_run=args.dry_run)


if __name__ == "__main__":
    cli_main()
