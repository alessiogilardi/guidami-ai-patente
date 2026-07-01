# Data sources

## Main files

| File | Description |
|---|---|
| `data/docs/domande AB italiano 23 04 2025.pdf` | Official question bank for categories A/B, Italian, April 2025 |
| `data/parsed/quiz-patente-ab/` | Parser output (`uv run parse-domande`) |
| `data/parsed/cds/codice_della_strada.json` | CdS parsed by the normattiva scraper |
| `data/parsed/cap/codice_rca.json` | 96 CAP articles relevant to RCA/driving licence (subset of the full CAP) |
| `data/raw/cds/` | Raw HTML of the CdS (downloaded from normattiva.it) |
| `data/raw/cap/` | Raw HTML of the CAP |

## Scraping conventions

- Always preserve both raw (HTML/PDF) and parsed forms: allows re-parsing without re-downloading the data.
- Record the source URL and scraping timestamp on every document.
