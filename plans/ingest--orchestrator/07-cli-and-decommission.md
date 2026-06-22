# SP07 — CLI unica + decommissioning + doc

## Scopo singolo
**Cutover atomico**: introdurre l'unica CLI a sottocomandi, ripuntare `[project.scripts]`,
e rimuovere tutto il vecchio (pipeline/builder custom + 6 entry point). Aggiornare la doc.

## Dipende da
SP03, SP04, SP05, SP06 (tutti i flow + runner esistenti e verdi).

## Componenti

### Nuovo — `guidami_ai_patente_ingestor/cli.py`
`argparse` a sottocomandi; carica `IngestorConfig` + `LayerResolver` **una sola volta**
(pattern di `main.py:22-24`):
```
ingest prepare knowledge --source <cds|cap> [--force]   ingest index knowledge --source <cds|cap>   ingest reset knowledge
ingest prepare quiz [--force]                            ingest index quiz                           ingest reset quiz
```
- **Per-source (decisione 2026-06-22)**: per il dominio knowledge, `prepare` e `index` richiedono
  `--source` e girano **una source per esecuzione** (no loop interno). Quiz ha source unica
  (`quiz`) → `--source` superfluo (default implicito).
- `prepare` → flow factory (clean+enrich / quiz prep) per la `source` + skip idempotente per-source.
- `index`   → flow factory per la `source` + `flow.run()`. Lo store knowledge fa **delete-by-source**
  (`delete_source`), non `truncate`: run su source diverse non si sovrascrivono.
- `reset`   → `PostgresClient` + `*StoreRepository.truncate()` (wipe totale; logica attuale di
  `reset_db.py`/`reset_quiz_db.py`). `truncate` su `KnowledgeChunkStoreRepository` **resta** per questo.
- **`sources` da config** = catalogo delle source valide per validare `--source`
  (`PipelineLayerConfig.sources`, knowledge_* = `["cds","cap"]`, quiz_* = `["quiz"]`).
  Nessuna lista hardcoded nella CLI.

### Modificati
- **`pyproject.toml`** `[project.scripts]`: rimuovere `ingest-knowledge`, `ingest-quiz`,
  `prepare-knowledge`, `prepare-quiz`, `reset-knowledge-db`, `reset-quiz-db`; aggiungere
  `ingest = "guidami_ai_patente_ingestor.cli:main"`. Restano `scrape-*` / `parse-domande`.
- **`CLAUDE.md`**: tabella comandi (6 righe ingestor → sottocomandi `ingest …`).
- `__init__.py` di `orchestrators` e `services` ripuliti dai simboli rimossi.

### Eliminati
- `orchestrators/knowledge_indexing/`, `orchestrators/quiz_indexing/`,
  `orchestrators/knowledge_preparation/`, `orchestrators/quiz_preparation/` (8 file: pipeline+builder).
- `main.py`, `quiz_main.py`, `prepare_knowledge_main.py`, `quiz_preparation_main.py`,
  `reset_db.py`, `reset_quiz_db.py`.
- Relativi test dei vecchi pipeline/builder (sostituiti dai test step/flow di 03–06).

## TDD / verifica
- Test CLI: parsing sottocomandi → invoca la factory/runner corretti (con dipendenze fake/mock).
- Smoke: `ingest reset knowledge`/`reset quiz` → `truncate()` chiamato sulla tabella giusta.

## Verifica end-to-end (gate di chiusura)
1. `uv run ruff check src tests && uv run ruff format src tests && uv run pyright`
2. `uv run pytest`
3. `cd docker && docker compose up -d`, poi:
   `uv run ingest prepare quiz` / `prepare knowledge` (2° run → log skip),
   `uv run ingest index knowledge` / `index quiz`,
   `uv run ingest reset knowledge` / `reset quiz`.
4. Spot-check: conteggi righe `knowledge_chunks` / `quiz_questions` invariati vs baseline
   (quiz: 7098).

## Follow-up doc
Invocare l'agente `architecture-doc-keeper` per aggiornare `.claude/architectures/ingestor/*`
e i `plans/ingest--*` con il design effettivamente realizzato. Aggiornare la tabella comandi in `CLAUDE.md`.

## Done criteria
- Un solo entry point `ingest`; vecchio codice rimosso; gate e2e verde; doc aggiornata.
