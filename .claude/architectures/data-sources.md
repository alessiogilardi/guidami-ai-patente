# Sorgenti dati

## File principali

| File | Descrizione |
|---|---|
| `data/docs/domande AB italiano 23 04 2025.pdf` | Banca domande ufficiale categorie A/B, italiano, aprile 2025 |
| `data/parsed/quiz-patente-ab/` | Output del parser (`uv run parse-domande`) |
| `data/parsed/cds/codice_della_strada.json` | CdS parsato dallo scraper normattiva |
| `data/parsed/cap/codice_rca.json` | 96 articoli CAP rilevanti per RCA/patente (subset del CAP completo) |
| `data/raw/cds/` | HTML grezzo del CdS (scaricato da normattiva.it) |
| `data/raw/cap/` | HTML grezzo del CAP |

## Convenzioni di scraping

- Conservare sempre sia il raw (HTML/PDF) sia il parsed: permette di ri-parsare senza dover riscaricarne i dati.
- Registrare URL sorgente e timestamp di scraping su ogni documento.
