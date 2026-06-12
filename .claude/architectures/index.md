# Architetture implementate — indice

Questa cartella documenta le decisioni architetturali **effettivamente
implementate** nel codice, a differenza di `plans/` che contiene la
progettazione (anche per parti non ancora costruite).

Quando un piano in `plans/` viene implementato, la decisione rilevante va
riportata qui in forma sintetica, con riferimento al piano originale per il
contesto/motivazione completa.

## Documenti

- [infrastructure.md](infrastructure.md) — Postgres/pgvector via Docker
  compose, schema `knowledge_chunks`
- [commons.md](commons.md) — package `src/commons/`: modelli, client
  embedding e vector store, config condivise
- [ingestor.md](ingestor.md) — package `src/guidami_ai_patente_ingestor/`:
  pipeline di indicizzazione CdS + CAP (load → chunk → embed → store)

## Stato implementazione (vedi plans/architecture-index.md per il quadro completo)

| Componente | Stato |
|---|---|
| Docker compose + `db/init.sql` | ✅ implementato |
| `src/commons/` (models, clients, configs) | ✅ implementato |
| `guidami_ai_patente_ingestor/` | ✅ implementato |
| `guidami_ai_patente/` (app FastAPI) | ⬜ non avviato |
