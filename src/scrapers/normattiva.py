"""Scraper for normattiva.it — supports multiple Italian laws."""

from __future__ import annotations

import json
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
    slug: str         # used for directory and file naming
    toc_url: str      # normattiva.it URN URL with !vig=
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


class ArticleParams(TypedDict):
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
    numero: str
    titolo: str
    text: str
    commi: list[str]
    url: str
    scraped_at: str
    abrogato: bool


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

    pre_comma = soup.find(class_="article-pre-comma-text-akn")
    text = pre_comma.get_text(separator=" ", strip=True) if pre_comma else ""

    commi: list[str] = []
    for comma_div in soup.find_all(class_="art-comma-div-akn"):
        num_span = comma_div.find(class_="comma-num-akn")
        text_span = comma_div.find(class_="art_text_in_comma")
        if not text_span:
            continue
        prefix = num_span.get_text(strip=True) + " " if num_span else ""
        commi.append(prefix + text_span.get_text(separator=" ", strip=True))

    abrogato = bool(soup.find(class_="abrogato")) or "abrogato" in html.lower()

    return ArticleRecord(
        numero=numero,
        titolo=titolo,
        text=text,
        commi=commi,
        url=url,
        scraped_at=datetime.now(UTC).isoformat(),
        abrogato=abrogato,
    )


def _headers(toc_url: str) -> dict[str, str]:
    return {**_BASE_HEADERS, "Referer": toc_url}


def _refresh_session(client: httpx.Client, toc_url: str) -> None:
    try:
        client.get(toc_url, headers=_headers(toc_url))
    except httpx.RequestError:
        pass


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
    raw_dir = Path("data/raw") / law["slug"]
    processed_dir = Path("data/processed") / law["slug"]
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

        for i, params in enumerate(articles_params, start=1):
            suffix = _sotto_articolo_suffix(params["idSottoArticolo"])
            label = f"Art. {params['idArticolo']}{suffix}"
            url = _build_article_url(params)
            raw_filename = (
                f"art_{int(params['idArticolo']):04d}_{params['idSottoArticolo']}.html"
            )

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

            record = _parse_article(raw_html, url)
            records.append(record)
            print(f"OK — {record['titolo'] or '(senza titolo)'}")

            time.sleep(DELAY_SECONDS)

        output_path = processed_dir / law["output_name"]
        output_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nDone. {len(records)} articles saved to {output_path}")


def main_cds() -> None:
    main(CDS)


def main_cap() -> None:
    main(CAP)


if __name__ == "__main__":
    main_cds()
