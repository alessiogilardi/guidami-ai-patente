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
  knowledge preparation e indexing su flow flowstep per-source; quiz indexing
  su flow flowstep e quiz preparation su due flow a specchio del knowledge
  (SP09: `parsed`→`cleaned`→`enriched`, flatten+dedup spostato a `cleaning`);
  catena modelli knowledge un-modello-per-layer (`ParsedArticleModel`/
  `EnrichedArticleModel`/`EmbeddableChunkModel`/`KnowledgeChunk`); modelli quiz
  un-modello-per-layer (`ParsedQuizModel`/`CleanedQuizModel`/
  `EnrichedQuizModel`/`EmbeddableQuizModel`); l'enrichment quiz è oggi
  costruito sui building block generici `MapStep`/`EnrichDataStep` (sostituiti
  i precedenti step/service quiz-specific `EnrichQuizStep`/
  `QuizEnrichmentService`/`Protocol QuizEnricher`, rimossi come duplicazione);
  unico entry point `cli.py` con sottocomandi `ingest prepare/index/reset`
  (SP07, sostituisce `main.py`/`reset_db.py`/`reset_quiz_db.py`);
  dettaglio in `ingestor/data_preparation.md`, `ingestor/knowledge_pipelines.md`,
  `ingestor/quiz_pipelines.md`, `ingestor/config_and_entrypoints.md`,
  `ingestor/flowstep_toolkit.md`, `ingestor/tests.md`

## Stato implementazione (vedi plans/architecture-index.md per il quadro completo)

| Componente | Stato |
|---|---|
| Docker compose + `db/init.sql` | ✅ implementato |
| `src/commons/` (models, clients, configs, agents) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — data preparation (LLM enrichment) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — step flowstep generici (`EmbedStep`, `DbStoreStep`, `LoadJsonStep`, `MapStep`, `WriteJsonStep`, `StoreRepository`, `context_keys`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge indexing flow per-source (`ChunkArticlesStep`, `EmbedChunksStep`, `MapStep("map_to_chunk_entity")` generico, `StoreChunksStep`, `build_knowledge_indexing_flow` — 5 step; `EmbeddableChunkModel` con `embedded_text`; `ArticleMapper.from_embeddable_chunk_to_knowledge_chunk`; `KnowledgeChunkStoreRepository.delete_source`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz indexing flow (`MapToEmbeddableStep`, `build_quiz_indexing_flow`, `DbStoreStep` generico truncate full-reload; `LoadEnrichedQuizStep`/`MapToQuizEntityStep` sostituiti dai generici `LoadJsonStep`/`MapStep`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz data model un-modello-per-layer (`ParsedQuizModel`/`ParsedQuizItemModel`/`CleanedQuizModel`/`EnrichedQuizModel`/`EmbeddableQuizModel` in `models/quiz/`; `entities/` ingestor solo `Article`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — consolidamento mapper quiz (`QuizMapper` unico, flatten+dedup nello step dedicato per ciascun layer) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge preparation flow + runner generico (`build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`, `run_preparation`, generici `LoadJsonStep`/`MapStep`/`WriteJsonStep`/`EnrichDataStep` + `ContextEnricher` domain-specific, `ArticleMapper`; catena `ParsedArticleModel`→`EnrichedArticleModel`→`EmbeddableChunkModel`→`KnowledgeChunk`; rimossi `ContextualizeStep` e `EnrichedArticleMapper`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz preparation flow a due stadi (SP09: `build_quiz_cleaning_flow` con `FlattenQuizStep` per il flatten+dedup `parsed`→`cleaned`, layer `parsed` introdotto per il quiz; sostituisce il precedente flow unico) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — refactor enrichment quiz su building block generici (`build_quiz_enrichment_flow` con `MapStep` (base-map) + `EnrichDataStep`/`EnricherProtocol` generici + `ImageDescriptionEnricher`; rimossi `EnrichQuizStep`, `QuizEnrichmentService`, `Protocol QuizEnricher` come duplicazione dei generici già esistenti) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — cutover CLI preparation + rimozione pipeline legacy residue | ✅ implementato |
| `guidami_ai_patente/` (app FastAPI) | ⬜ non avviato |
