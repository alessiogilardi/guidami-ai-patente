# Architetture implementate — indice

Questa cartella documenta le decisioni architetturali **effettivamente
implementate** nel codice, a differenza di `plans/` che contiene la
progettazione (anche per parti non ancora costruite).

Quando un piano in `plans/` viene implementato, la decisione rilevante va
riportata qui in forma sintetica, con riferimento al piano originale per il
contesto/motivazione completa.

## Documenti

- [tech-stack.md](tech-stack.md) — panoramica cross-cutting del tech stack: package
  management, storage, embedding, agenti LLM, librerie principali
- [infrastructure.md](infrastructure.md) — Postgres/pgvector via Docker
  compose, schema `knowledge_chunks` (incl. colonna `context`)
- [commons.md](commons.md) — package `src/commons/`: modelli, entità, client
  embedding e vector store, `Agent`/`AgentImpl`, config condivise
- [ingestor/index.md](ingestor/index.md) — package `src/guidami_ai_patente_ingestor/`:
  pipeline/flow batch (preparation + indexing) per corpus normativo e quiz bank;
  knowledge preparation e indexing ricostruiti su flow flowstep per-source
  (SP03/SP05); quiz indexing su flow flowstep (SP04, mapper consolidato in
  SP04-tris) e quiz preparation su flow flowstep costruito da zero (SP06);
  modelli quiz rinominati/spostati in `models/quiz/` (SP04-bis); dettaglio in
  `ingestor/data_preparation.md`, `ingestor/knowledge_pipelines.md`,
  `ingestor/quiz_pipelines.md`, `ingestor/config_and_entrypoints.md`,
  `ingestor/flowstep_toolkit.md`, `ingestor/tests.md`

## Stato implementazione (vedi plans/architecture-index.md per il quadro completo)

| Componente | Stato |
|---|---|
| Docker compose + `db/init.sql` | ✅ implementato |
| `src/commons/` (models, clients, configs, agents) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — data preparation (LLM enrichment) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — step flowstep generici (SP02: `EmbedStep`, `DbStoreStep`, `StoreRepository`, `context_keys`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge indexing flow per-source (SP03: `LoadEnrichedArticlesStep`, `ChunkArticlesStep`, `EmbedChunksStep`, `StoreChunksStep`, `build_knowledge_indexing_flow`, `KnowledgeChunkStoreRepository.delete_source`, `PostgresClient.execute`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz indexing flow (SP04: `LoadEnrichedQuizStep`, `MapToEmbeddableStep`, `MapToQuizEntityStep`, `build_quiz_indexing_flow`, `DbStoreStep` generico truncate full-reload) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz data model rename/move (SP04-bis: `QuizBankModel`/`QuizBankItemModel`/`EnrichedQuizModel`/`EnrichedQuizItemModel`/`EmbeddableQuizModel` in `models/quiz/`; `entities/` ingestor solo `Article`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — consolidamento mapper quiz (SP04-tris: `QuizMapper` unico, flatten+dedup migrato in `MapToEmbeddableStep`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge preparation flow + runner generico (SP05: `build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`, `run_preparation`, step `Load*`/`Clean*`/`Write*`/`Contextualize*`, `EnrichedArticleMapper`; sostituisce `DataPreparationPipeline` rimossa) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz preparation flow (SP06: `build_quiz_preparation_flow`, step `LoadQuizStep`/`EnrichQuizStep`/`WriteEnrichedQuizStep`, `services/quiz/` con `QuizEnricher`/`QuizEnrichmentService`/`ImageDescriptionEnricher`, riuso `run_preparation`; greenfield, nessuna pipeline preesistente) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — cutover CLI preparation + rimozione pipeline legacy residue (SP07) | ⬜ non avviato |
| `guidami_ai_patente/` (app FastAPI) | ⬜ non avviato |
