"""Scraper for normattiva.it — supports multiple Italian laws."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import parse_qs, urlencode

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

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


class LawConfig(TypedDict):
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


class ArticleParams(TypedDict):
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


class ArticleRecord(TypedDict):
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
    as the title, since it is the descriptive one. Returns
    `(title, remaining_text)`. If no leading title segment is found at all
    (no leading `(`, a leading `((`, or no closing `)`), returns
    `("", body_text)` unchanged and logs a `warning` naming `article_number`.
    """
    remaining = body_text.lstrip()
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
    - the nearest non-whitespace character before it is `)` (the close of a
      preceding parenthetical aside or amendment bracket, e.g. `...M.C.T.C..))
      2. Nell'evenienza...`) — always a genuine boundary;
    - the nearest non-whitespace character before it is `.` and the word
      immediately before that period is not one of
      `_MARKER_FALSE_POSITIVE_PREFIXES` (abbreviations such as "art.", "n.",
      "fig." that also end in digit+period but do not start a new comma).
    """
    if start == 0 or not text[:start].strip("( "):
        return True
    if start >= 2 and text[start - 2 : start] == "((":
        return True
    match = re.search(r"([.)])\s+$", text[:start])
    if match is None:
        return False
    if match.group(1) == ")":
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
        if flag != "0":
            continue

        id_art = get("idArticolo")
        id_sotto = get("idSottoArticolo")
        key = (id_art, id_sotto)
        if key in seen:
            continue
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

    results.sort(key=lambda p: (int(p["idArticolo"]), int(p["idSottoArticolo"])))
    return results


def _build_article_url(params: ArticleParams) -> str:
    qs = {
        "art.versione": params["versione"],
        "art.idGruppo": params["idGruppo"],
        "art.flagTipoArticolo": params["flagTipoArticolo"],
        "art.codiceRedazionale": params["codiceRedazionale"],
        "art.idArticolo": params["idArticolo"],
        "art.idSottoArticolo": params["idSottoArticolo"],
        "art.idSottoArticolo1": params["idSottoArticolo1"],
        "art.dataPubblicazioneGazzetta": params["dataPubblicazioneGazzetta"],
        "art.progressivo": params["progressivo"],
    }
    return f"{ARTICLE_URL}?{urlencode(qs)}"


def _parse_article(html: str, url: str) -> ArticleRecord:
    """Extract structured data from an article's HTML page."""
    soup = BeautifulSoup(html, "html.parser")

    num_tag = soup.find(class_="article-num-akn")
    numero_raw = num_tag.get_text(strip=True) if num_tag else ""
    numero = re.sub(r"^Art\.\s*", "", numero_raw)

    heading_tag = soup.find(class_="article-heading-akn")
    titolo = heading_tag.get_text(strip=True).strip("().") if heading_tag else ""

    # FR-1/FR-2/FR-3/FR-4: structured comma numbers, list bodies kept, list items
    # merged into the comma that introduces them, note fragments discarded.
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

    # FR-5: a missing title falls back to the unnumbered pre-comma block; a numbered
    # pre-comma block is a comma, not a title (prepended so it stays first).
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

    # FR-13: article-level repeal is anchored to the repeal formula in
    # `art-just-text-akn`, not to a substring match anywhere in the page.
    just_text_tag = soup.find(class_="art-just-text-akn")
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

    # FR-14: `art-just-text-akn` is a fourth body container, subject to the same
    # rules — but the pure repeal formula is consumed by FR-13 above, not emitted
    # as a comma.
    if just_text_tag is not None and not abrogato:
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


def main(law: LawConfig) -> None:
    """Download the legal text specified by `law` and save it to `data/parsed/`."""
    raw_dir = Path("data/raw") / law["slug"]
    processed_dir = Path("data/parsed") / law["slug"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    toc_url = law["toc_url"]
    headers = _headers(toc_url)

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        print(f"Fetching TOC for {law['slug']}…")
        toc_resp = client.get(toc_url, headers=headers)
        toc_resp.raise_for_status()

        toc_html = toc_resp.text
        (raw_dir / "toc.html").write_text(toc_html, encoding="utf-8")

        articles_params = _parse_toc(toc_html)
        print(f"Found {len(articles_params)} articles in TOC.")

        records: list[ArticleRecord] = []
        skipped_parse_errors: list[str] = []

        for i, params in enumerate(articles_params, start=1):
            suffix = _sotto_articolo_suffix(params["idSottoArticolo"])
            label = f"Art. {params['idArticolo']}{suffix}"
            url = _build_article_url(params)
            raw_filename = f"art_{int(params['idArticolo']):04d}_{params['idSottoArticolo']}.html"

            print(f"[{i}/{len(articles_params)}] {label}…", end=" ", flush=True)

            resp = _fetch_with_retry(client, url, toc_url)
            if resp is None:
                print("SKIP (fetch failed)")
                continue

            raw_html = resp.text

            # Detect session expiry: valid article pages always contain this class
            if "article-num-akn" not in raw_html:
                print("session invalid — refreshing…", end=" ", flush=True)
                _refresh_session(client, toc_url)
                time.sleep(5)
                resp = _fetch_with_retry(client, url, toc_url)
                if resp is None or "article-num-akn" not in resp.text:
                    print("SKIP (still failing after session refresh)")
                    continue
                raw_html = resp.text

            (raw_dir / raw_filename).write_text(raw_html, encoding="utf-8")

            try:
                record = _parse_article(raw_html, url)
            except ValueError as exc:
                print(f"SKIP (parse error): {exc}")
                logger.warning("Skipping %s due to parse error: %s", label, exc)
                skipped_parse_errors.append(label)
            else:
                records.append(record)
                print(f"OK — {record['title'] or '(untitled)'}")

            time.sleep(DELAY_SECONDS)

        output_path = processed_dir / law["output_name"]
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nDone. {len(records)} articles saved to {output_path}")
        if skipped_parse_errors:
            print(
                f"{len(skipped_parse_errors)} article(s) skipped due to parse errors: "
                f"{', '.join(skipped_parse_errors)}"
            )


def main_cds() -> None:
    """Entry point for scraping the Codice della Strada."""
    main(CDS)


def main_cap() -> None:
    """Entry point for scraping the Codice delle Assicurazioni Private."""
    main(CAP)


def main_reg() -> None:
    """Entry point for scraping the Regolamento di esecuzione e di attuazione."""
    main(REG)


if __name__ == "__main__":
    main_cds()
