# Refactor degli `orchestrators/` sopra il framework `commons/flowstep`

> **Decomposizione operativa**: questo piano master è spezzato in 7 sotto-piani a scopo
> singolo in [`ingest--orchestrator/index.md`](ingest--orchestrator/index.md). Implementare
> seguendo quell'indice; questo documento resta il razionale complessivo.

## Context

`src/guidami_ai_patente_ingestor/orchestrators/` ha 4 sottopacchetti (`knowledge_indexing`, `knowledge_preparation`, `quiz_indexing`, `quiz_preparation`), ciascuno con un `*Pipeline` + un `*PipelineBuilder` (8 file) e logica di batching embedding **duplicata verbatim** tra i due indexing. Più 6 entry point CLI.

È stato introdotto in `src/commons/flowstep` un framework di pipeline condiviso (**StreamLine/FlowStep**): `Flow` esegue una lista lineare di `Step` che comunicano via un `FlowContext` (dict a chiavi stringa); `FlowBuilder` assembla e valida il contratto di chiavi (required/produced). Obiettivo: **ricostruire le pipeline di ingestion sopra flowstep**, eliminando i `*Pipeline`/`*PipelineBuilder` custom, e consolidare i 6 entry point in **una CLI unica**.

### Stato del framework (verificato)
- API stabile: `Flow.run(initial_context) -> FlowContext`; `Step.execute(ctx)` + `get_required_keys()` + `get_produced_keys()`; `FlowBuilder(name).add_step(...).build(validate=True, initial_context=...)`; `FlowContext.put/get/has/keys`; validazione contratto chiavi + `FlowExecutionError`/`FlowValidationError`.
- **Non usare**: il layer tipizzato (`execute_typed`, `initial_context_model`) **non è implementato** (param accettato ma ignorato; il README è obsoleto). flowstep è WIP: ci appoggiamo solo alla superficie stabile sopra.

## Decisioni (Q&A)
1. **flowstep al posto degli orchestrator**: sì. I `*Pipeline`/`*PipelineBuilder` custom vengono eliminati; `FlowBuilder` è il builder.
2. **Idempotenza (skip-se-esiste), loop per-source (cds/cap), checkpoint `cleaned`**: **fuori dal Flow**, in un runner generico in `orchestrators/`, invocato dalla CLI. Il Flow resta lineare e puro.
3. **Tipizzazione del context**: **costanti per le chiavi** (no magic string) + payload già tipizzati (oggetti/`list` pydantic) + **cast espliciti** a `context.get(...)` ai confini.
4. **CLI unica** con sottocomandi (unico punto mantenuto dal piano precedente).

## Mappatura pipeline → Flow di Step

| Pipeline | Step (lineari) |
|---|---|
| **Knowledge indexing** | `LoadEnrichedArticles` (cds+cap) → `ChunkArticles` → `EmbedStep` → `StoreChunks` |
| **Quiz indexing** | `LoadEnrichedQuiz` → `MapToEmbeddable` → `EmbedStep` → `MapToQuizEntity` → `StoreQuizQuestions` |
| **Knowledge prep — stage clean** | `LoadParsedArticles` → `CleanArticles` → `WriteCleaned` |
| **Knowledge prep — stage enrich** | `LoadCleanedArticles` → `Contextualize` → `WriteEnriched` |
| **Quiz prep** | `LoadQuiz` → `DescribeImages` (dedup + enrich) → `WriteEnrichedQuiz` |

Idempotenza/loop/checkpoint **non** sono Step: il runner cicla i source, controlla `output_path.exists()` e fa lo `skip`, poi `flow.run({SOURCE: source})`.

## Componenti da realizzare

### Principio Step ⟷ Service (disaccoppiamento)
Ogni `Step` è un **adattatore sottile** a flowstep: legge/scrive il `FlowContext` (con cast ai confini) e **delega** la logica di dominio. Se la logica è banale può restare nello Step; se è **non-triviale va in un service/mapper dedicato** — testabile e riusabile anche dalla futura app — e lo Step si limita a `get → chiama service → put`. Non si accoppia la logica di dominio al framework di pipeline.

### 1. Costanti chiavi context — `orchestrators/context_keys.py`
Costanti `str` per ogni chiave: `SOURCE`, `ARTICLES_BY_SOURCE`, `CHUNKS`, `PARSED_ARTICLES`, `CLEANED_ARTICLES`, `ENRICHED_ARTICLES`, `ENRICHED_QUIZ`, `EMBEDDABLE_QUIZ`, `QUIZ_ENTITIES`, `PARSED_QUIZ`, ecc. Usate da tutti gli Step in `get_required_keys`/`get_produced_keys`/`execute`.

### 2. Embedding: client → service → step (tre livelli disaccoppiati)
Oggi esiste solo `EmbeddingClient` (adapter I/O) e il batching è duplicato dentro le pipeline. Separare:
- **`HasEmbeddableText`** (Protocol, in `commons`): `embedded_text: str` (sola lettura) — *"un embeddable che restituisce il testo"*. `Embeddable` estende il protocollo con `embedding: list[float] | None` (campo scrivibile), usato solo dal wrapper.
- **`EmbeddingService(client, batch_size)`** (in `commons`, accanto al client): riceve `Sequence[HasEmbeddableText]`, fa il **batching** (unico home, sostituisce i due `_assign_embeddings`), chiama `client.embed_passages([i.embedded_text ...])` e **ritorna i vettori allineati**. Puro: nessuna mutazione dei modelli. `batch_size` iniettato come `int` (commons resta libero da `pydantic-settings`).
- **`EmbedStep(name, embedding_service, items_key)`** (wrapper flowstep): `get` items dal context → `embedding_service.embed(items)` → **assegna ogni vettore al campo `embedding`** del modello pydantic (`item.embedding = vector`, `zip(strict=True)`) → `put`. È il "wrapper esterno che assegna l'embedding al campo corretto". `required/produced = {items_key}`.

Risultato: client (I/O) ⟂ service (testo→vettori + batching) ⟂ step (context + assegnazione campo).

### 2-bis. Altri step generici riusabili (in `services/`)
- **`DbStoreStep(name, store_repo, items_key)`** — sink terminale: `store_repo.truncate(); store_repo.bulk_insert(items)`. Funziona con `KnowledgeChunkStoreRepository` e `QuizQuestionStoreRepository` (stesse primitive). `required = {items_key}`, `produced = set()`.
- (Opportunità) `JsonLoadStep`/`JsonWriteStep` generici parametrizzati su repo+layer per i prep stage, se la firma `load(path)`/`write(items, path)` è condivisa.

### 3. Step di trasformazione di dominio (sottili) + service/mapper estratti
Gli Step wrappano i metodi privati degli attuali pipeline ma restano **sottili**: la logica non-triviale va estratta in service/mapper dedicati (principio sopra).

- Knowledge: `LoadEnrichedArticlesStep` (multi-source → `ARTICLES_BY_SOURCE`), `ChunkArticlesStep` (delega `ArticleChunker`, filtra `is_repealed` con `embed_repealed`), `LoadParsedArticlesStep`/`LoadCleanedArticlesStep`, `CleanArticlesStep` (delega `ArticleCleaner`), `ContextualizeStep` (delega `ArticleContextualizer`), `WriteCleanedStep`/`WriteEnrichedStep` (repo + resolver, legge `SOURCE`).
- Quiz: `LoadEnrichedQuizStep`, `MapToEmbeddableStep` (`QuizQuestionMapper`), `MapToQuizEntityStep` (`EmbeddableQuizQuestionMapper.to_entity`), `LoadQuizStep`, `DescribeImagesStep` (delega service sotto), `WriteEnrichedQuizStep`, sink via `DbStoreStep`.

**Service/mapper da estrarre** (logica oggi inline nei pipeline, troppo complessa per stare nello step):
- `ImageDescriptionService` (`services/quiz/`) — dedup `image_filename` unici + `RoadSignDescriber.describe` per immagine + skip/log errori → `dict[filename, str]`. Sostituisce `_describe_unique_images`. `DescribeImagesStep` resta sottile.
- `EnrichedArticleMapper` (`mappers/knowledge/`) — `Article + contexts → EnrichedArticle`. Sostituisce `_enrich`. `ContextualizeStep` chiama contextualizer + mapper.
- `EnrichedQuizMapper` (`mappers/quiz/`) — `QuizMainQuestion + descriptions → EnrichedQuizMainQuestion`. Sostituisce `_enrich_questions`.

Tutte le dipendenze (repo, service, resolver, config-derivati) iniettate nel **costruttore** dello Step; config caricata solo all'entry point. Re-export negli `__init__.py`.

### 4. Flow factory — `orchestrators/knowledge_flows.py`, `orchestrators/quiz_flows.py`
Funzioni che assemblano i `Flow` via `FlowBuilder(...).add_step(...).build(validate=True)`:
`build_knowledge_indexing_flow(config, resolver) -> Flow`, `build_knowledge_cleaning_flow`, `build_knowledge_enrichment_flow`, `build_quiz_indexing_flow`, `build_quiz_preparation_flow`. Iniettano gli Step concreti con le dipendenze.

### 5. Runner generico — `orchestrators/preparation_runner.py`
`run_preparation(flow, sources, output_layer, layer_resolver, force) -> None`: per ogni source, salta se `output` esiste (e non `force`), altrimenti `flow.run({SOURCE: source})`. Knowledge prep = due chiamate (clean→`cleaned`, enrich→`enriched`); quiz prep = una. Indexing: nessun runner, la CLI fa `build_*_flow(...).run()`.

### 6. CLI unica — `cli.py`
`argparse` a sottocomandi; carica `IngestorConfig` + `LayerResolver` una volta:
```
ingest prepare knowledge [--force]   ingest index knowledge   ingest reset knowledge
ingest prepare quiz      [--force]   ingest index quiz        ingest reset quiz
```
`prepare` → flow factory + `run_preparation`; `index` → flow factory + `flow.run()`; `reset` → `PostgresClient` + `*StoreRepository.truncate()` (logica attuale di `reset_db.py`).

## File: nuovi / modificati / eliminati

**Nuovi**: in `commons` — `HasEmbeddableText`/`Embeddable` (protocol) + `EmbeddingService`. In ingestor — `orchestrators/{context_keys,knowledge_flows,quiz_flows,preparation_runner}.py`; step generici (`EmbedStep`, `DbStoreStep`); step di dominio in `services/knowledge/steps/*` e `services/quiz/steps/*`; `services/quiz/image_description_service.py`; `mappers/knowledge/enriched_article_mapper.py`, `mappers/quiz/enriched_quiz_mapper.py`; `cli.py`.

**Modificati**: `pyproject.toml` (`[project.scripts]`: i 6 script ingestor → `ingest = "guidami_ai_patente_ingestor.cli:main"`; restano `scrape-*`/`parse-domande`); gli `__init__.py` di `services` e `orchestrators`; `CLAUDE.md` (tabella comandi).

**Eliminati**: `orchestrators/{knowledge_indexing,quiz_indexing,knowledge_preparation,quiz_preparation}/` (8 file); `main.py`, `quiz_main.py`, `prepare_knowledge_main.py`, `quiz_preparation_main.py`, `reset_db.py`, `reset_quiz_db.py`.

## TDD / test (test prima dell'implementazione)
Riorganizzare `tests/.../orchestrators/` + nuovi test in `tests/.../services/.../steps/`. Scrivere prima, verificarli rossi, poi implementare:
- **Step generici**: `EmbedStep` (batching, set in place, `zip(strict=True)`, required/produced keys); `DbStoreStep` (ordine truncate→bulk_insert con fake repo).
- **Step di dominio**: `ChunkArticlesStep` (filtro repealed), `CleanArticlesStep`, `ContextualizeStep`, `MapToEmbeddableStep`, `MapToQuizEntityStep`, `DescribeImagesStep` (dedup + skip immagine mancante).
- **Service estratti**: `EmbeddingService`, `ImageDescriptionService`, `EnrichedArticleMapper`, `EnrichedQuizMapper`.
- **Flow factory**: `build(validate=True)` non produce ERROR; `required_input_keys` attesi (es. `{SOURCE}` per i prep).
- **Runner**: skip se output esiste, `force=True` rigenera, itera i source.
- **Integration** (`@pytest.mark.integration`): flow completi indexing su Postgres.

## Verifica end-to-end
1. `uv run ruff check src tests && uv run ruff format src tests && uv run pyright`
2. `uv run pytest`
3. `cd docker && docker compose up -d`, poi: `uv run ingest prepare quiz`/`prepare knowledge` (2° run → log skip), `uv run ingest index knowledge`/`index quiz`, `uv run ingest reset knowledge`/`reset quiz`.
4. Spot-check: conteggi righe in `knowledge_chunks`/`quiz_questions` invariati rispetto a prima.

## Note / rischi
- flowstep è WIP: usare solo `Flow/Step/FlowContext/FlowBuilder` + validazione. Non dipendere da `execute_typed`/`initial_context_model`. Se in futuro arriva il layer tipizzato, gli Step si potranno migrare senza toccare i Flow.
- Side-effect nei sink (`DbStoreStep`, `Write*Step`): accettati come terminatori di pipeline.

## Follow-up doc
Al termine, invocare l'agente `architecture-doc-keeper` per aggiornare `.claude/architectures/ingestor/*` e i `plans/ingest--*`; aggiornare la tabella comandi in `CLAUDE.md`.
