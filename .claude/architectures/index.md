# Architetture implementate — indice

Questa cartella documenta le decisioni architetturali **effettivamente
implementate** nel codice, a differenza di `plans/` che contiene la
progettazione (anche per parti non ancora costruite).

Quando un piano in `plans/` viene implementato, la decisione rilevante va
riportata qui in forma sintetica, con riferimento al piano originale per il
contesto/motivazione completa.

## Documenti

- [code-conventions.md](code-conventions.md) — convenzioni specifiche del progetto: Pydantic frozen, cast `%s::vector` psycopg, marker `@pytest.mark.integration`
- [tech-stack.md](tech-stack.md) — panoramica cross-cutting del tech stack: package
  management, storage, embedding, agenti LLM, librerie principali
- [infrastructure.md](infrastructure.md) — Postgres/pgvector via Docker
  compose, schema `knowledge_chunks` (incl. colonna `context`)
- [commons.md](commons.md) — package `src/commons/`: modelli, entità, client
  embedding e vector store, `Agent`/`AgentImpl`, config condivise; `use_cases/`
  con `UseCase[T_In, T_Out]` (parametro `request`, `@final __call__`),
  `AsyncUseCase`, `ForEach[T, U]`
- [ingestor/index.md](ingestor/index.md) — package `src/guidami_ai_patente_ingestor/`:
  pipeline/flow batch (preparation + indexing) per corpus normativo e quiz bank;
  `flowstep` package top-level (SP00b, `src/flowstep/`) con `ApplyStep` in
  `src/flowstep/steps/`; tutti i flow builder usano `ApplyStep+ForEach` (SP04,
  `MapStep`/`EnrichDataStep`/`EnricherProtocol` rimossi); service quiz
  `FlattenQuiz`/`ToEmbeddableQuiz` (UseCase, ex step flowstep, SP02/SP03);
  enricher (`ContextEnricher`, `ImageDescriptionEnricher`) ora implementano
  `UseCase` (SP01); catena modelli knowledge un-modello-per-layer; modelli quiz
  un-modello-per-layer; unico entry point `cli.py` con sottocomandi `ingest
  prepare/index/reset`; dettaglio in `ingestor/data_preparation.md`,
  `ingestor/knowledge_pipelines.md`, `ingestor/quiz_pipelines.md`,
  `ingestor/config_and_entrypoints.md`, `ingestor/flowstep_toolkit.md`,
  `ingestor/tests.md`

## Stato implementazione (vedi plans/architecture-index.md per il quadro completo)

| Componente | Stato |
|---|---|
| Docker compose + `db/init.sql` | ✅ implementato |
| `src/commons/` (models, clients, configs, agents, `use_cases/` con `UseCase`/`AsyncUseCase`/`ForEach`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — data preparation (LLM enrichment) | ✅ implementato |
| `src/flowstep/` (package top-level, SP00b) + `ApplyStep` in `flowstep/steps/` (SP04) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — step flowstep generici (`EmbedStep`, `DbStoreStep`, `LoadJsonStep`, `WriteJsonStep`, `StoreRepository`, `context_keys`; `MapStep`/`EnrichDataStep`/`EnricherProtocol` RIMOSSI in SP04) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge indexing flow per-source (`ChunkArticlesStep`, `EmbedChunksStep`, `ApplyStep("map_to_chunk_entity", ForEach(...))`, `StoreChunksStep`, `build_knowledge_indexing_flow` — 5 step; `EmbeddableChunkModel`; `ArticleMapper`; `KnowledgeChunkStoreRepository.delete_source`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz indexing flow (`build_quiz_indexing_flow` con `ApplyStep(ToEmbeddableQuiz())` + `ApplyStep(ForEach(...))`, `DbStoreStep` truncate full-reload; `MapToEmbeddableStep` RIMOSSO → `ToEmbeddableQuiz` service UseCase, SP03) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz data model un-modello-per-layer (`ParsedQuizModel`/`ParsedQuizItemModel`/`CleanedQuizModel`/`EnrichedQuizModel`/`EmbeddableQuizModel` in `models/quiz/`; `entities/` ingestor solo `Article`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — consolidamento mapper quiz (`QuizMapper` unico; `from_enriched_to_embeddable(item)` 1 argomento, modello flat; flatten+dedup nei service `FlattenQuiz`/`ToEmbeddableQuiz`, non più negli step) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — knowledge preparation flow + runner generico (`build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`, `run_preparation`, `ApplyStep+ForEach`+`ContextEnricher` (UseCase, SP01), `ArticleMapper`; catena `ParsedArticleModel`→`EnrichedArticleModel`→`EmbeddableChunkModel`→`KnowledgeChunk`) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — quiz preparation flow a due stadi (SP09: `build_quiz_cleaning_flow` con `ApplyStep(FlattenQuiz())` `parsed`→`cleaned`; SP04: `FlattenQuizStep` rimosso, logica in `FlattenQuiz` service UseCase) | ✅ implementato |
| `guidami_ai_patente_ingestor/` — refactor SP04: `ApplyStep+ForEach` sostituiscono `MapStep`/`EnrichDataStep` in tutti i flow; `FlattenQuiz`/`ToEmbeddableQuiz` service UseCase (SP02/SP03); enricher implementano `UseCase` (SP01); `EnricherProtocol` rimosso | ✅ implementato |
| `guidami_ai_patente_ingestor/` — cutover CLI preparation + rimozione pipeline legacy residue | ✅ implementato |
| `guidami_ai_patente/` (app FastAPI) | ⬜ non avviato |
