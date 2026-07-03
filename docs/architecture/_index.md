# Architecture — Index

This directory documents architectural decisions **actually implemented** in the codebase.

## Documents

- [overview.md](overview.md) — cross-cutting tech stack: package management, storage,
  embedding, LLM agents, main libraries
- [patterns.md](patterns.md) — cross-cutting patterns: `UseCase[T_In, T_Out]`,
  `ForEach[T, U]`, `ApplyStep(ForEach(fn))` composition, `embedded_text` property
  convention, config loading pattern
- [data-sources.md](data-sources.md) — source files (PDF, parsed JSON, raw HTML),
  scraping conventions (raw + parsed, URL + timestamp)
- [database/_index.md](database/_index.md) — Postgres/pgvector via Docker Compose; schema
  `knowledge_chunks` and `quiz_questions`; conventions and migrations log
- [decisions/_index.md](decisions/_index.md) — Architecture Decision Records (ADRs)
- [modules/_index.md](modules/_index.md) — per-package documentation:
  - [modules/commons/overview.md](modules/commons/overview.md) — `src/domain/`: shared domain models, entities,
    embedding client and vector store, `Agent`/`AgentImpl`, shared configs; `use_cases/`
    with `UseCase[T_In, T_Out]`, `AsyncUseCase`, `ForEach[T, U]`
  - [modules/flowstep/_index.md](modules/flowstep/_index.md) — `src/flowstep/`: domain-agnostic
    sequential-pipeline framework; `Flow`, `Step`, `FlowBuilder`, `FlowContext`,
    `FlowValidator`, `ApplyStep`
  - [modules/ingestor/_index.md](modules/ingestor/_index.md) — `src/guidami_ai_patente_ingestor/`:
    batch pipeline/flow (preparation + indexing) for the normative corpus and quiz bank

## Implementation Status

| Component | Status |
|---|---|
| Docker Compose + `db/init.sql` | ✅ implemented |
| `src/domain/` (models, entities, clients, configs, agents, `use_cases/` with `UseCase`/`AsyncUseCase`/`ForEach`) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — data preparation (LLM enrichment) | ✅ implemented |
| `src/flowstep/` — sequential-pipeline framework (SP00b) + `ApplyStep` in `flowstep/steps/` (SP04) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — generic steps (`EmbedStep`, `DbStoreStep`, `LoadJsonStep`, `WriteJsonStep`, `StoreRepository`, `context_keys`; `MapStep`/`EnrichDataStep`/`EnricherProtocol` REMOVED in SP04) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — knowledge indexing flow per-source (`ChunkArticlesStep`, `EmbedChunksStep`, `ApplyStep("map_to_chunk_entity", ForEach(...))`, `StoreChunksStep`, `build_knowledge_indexing_flow` — 5 steps; `EmbeddableChunkModel`; `ArticleMapper`; `KnowledgeChunkStoreRepository.delete_source`) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — quiz indexing flow (`build_quiz_indexing_flow` with `ApplyStep(ToEmbeddableQuiz())` + `ApplyStep(ForEach(...))`, `DbStoreStep` truncate full-reload; `MapToEmbeddableStep` REMOVED → `ToEmbeddableQuiz` service UseCase, SP03) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — quiz data model one-model-per-layer (`ParsedQuizModel`/`ParsedQuizItemModel`/`CleanedQuizModel`/`EnrichedQuizModel`/`EmbeddableQuizModel` in `models/quiz/`; `entities/` ingestor only `Article`) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — quiz mapper consolidation (`QuizMapper` single; `from_enriched_to_embeddable(item)` 1 argument, flat model; flatten+dedup in services `FlattenQuiz`/`ToEmbeddableQuiz`, no longer in steps) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — knowledge preparation flow + generic runner (`build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`, `run_preparation`, `ApplyStep+ForEach`+`ContextEnricher` (UseCase, SP01), `ArticleMapper`; chain `ParsedArticleModel`→`EnrichedArticleModel`→`EmbeddableChunkModel`→`KnowledgeChunk`) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — two-stage quiz preparation flow (SP09: `build_quiz_cleaning_flow` with `ApplyStep(FlattenQuiz())` `parsed`→`cleaned`; SP04: `FlattenQuizStep` removed, logic moved to `FlattenQuiz` service UseCase) | ✅ implemented |
| `guidami_ai_patente_ingestor/` — SP04 refactor: `ApplyStep+ForEach` replace `MapStep`/`EnrichDataStep` in all flows; `FlattenQuiz`/`ToEmbeddableQuiz` service UseCase (SP02/SP03); enrichers implement `UseCase` (SP01); `EnricherProtocol` removed | ✅ implemented |
| `guidami_ai_patente_ingestor/` — CLI preparation cutover + removal of remaining legacy pipelines | ✅ implemented |
| `guidami_ai_patente_ingestor/` — `NormReferenceEnricher` + `NormReferenceDescriberAgent` + `QuizMetadata` entity (embedded value object in `domain/entities/quiz/`); `quiz_metadata JSONB` column on `quiz_questions`; wired into `build_quiz_enrichment_flow` after `ImageDescriptionEnricher` | ✅ implemented |
| `guidami_ai_patente/` (FastAPI app) | ⬜ not started |
