# Ingestor — Test

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`, `plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/04-bis-quiz-data-models.md`,
`plans/ingest--orchestrator/04-tris-quiz-mappers.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md`,
`plans/ingest--orchestrator/06-quiz-preparation-flow.md`,
`plans/ingest--orchestrator/07-cli-and-decommission.md`,
`plans/ingest--orchestrator/08-generic-map-to-step.md`,
`plans/ingest--orchestrator/09-quiz-flatten-at-preparation.md`.

## Test

### Repositories

- `tests/guidami_ai_patente_ingestor/repositories/test_article_repository.py` —
  `load`/`write` round-trip su fixture reali.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  round-trip `write`/`load` su `EnrichedArticle` con `contexts`.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_question_store_repository.py` —
  tutti i test marcati `@pytest.mark.integration` (richiedono il Postgres del
  compose): `truncate` + `bulk_insert` su `quiz_questions` con colonna
  `embedding`.

> **Nota (refactor `BulkInsertStoreRepository`)**: `QuizQuestionStoreRepository`
> e `KnowledgeChunkStoreRepository` condividono oggi la base generica
> `BulkInsertStoreRepository[T]` (vedi
> [knowledge_pipelines.md](knowledge_pipelines.md)) per `truncate`/`bulk_insert`.
> Non esiste un test unitario dedicato alla base stessa (è astratta, prefisso
> `_`, non re-esportata): la copertura passa solo dai test di integrazione
> sulle due sottoclassi concrete (`test_quiz_question_store_repository.py` qui
> sopra; il knowledge store è coperto via `test_knowledge_flows.py`, vedi
> sezione "Orchestrators — step knowledge indexing" sotto).

> **Nota (SP09)**: `test_quiz_bank_repository.py` e
> `test_enriched_quiz_bank_repository.py` non esistono più — i flow di quiz
> preparation usano oggi i generici `LoadJsonStep`/`WriteJsonStep`
> (parametrizzati con `model_class`), non `QuizBankRepository`/
> `EnrichedQuizBankRepository` direttamente nei flow. I due repository
> restano nel codice (`repositories/json/`) ma senza test dedicato corrente.

### Config e layer resolver

- `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  struttura `layers`/`sources`/selettori; `postgres: PostgresConnectionConfig`
  obbligatorio (`ValidationError` se assente con `_env_file=None`);
  immutabilità (`frozen=True`).
- `tests/guidami_ai_patente_ingestor/services/test_layer_resolver.py` —
  `path(layer, source)` compone correttamente; layer/source ignoti → errore.

### Services — knowledge

- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_cleaner.py` —
  su fixture reali (`tests/.../fixtures/cds_sample.json`, `cap_sample.json`):
  rimozione markup inline, rimozione ordinali, marcatori standalone, titolo
  avvolto in parentesi, ordinale duplicato (art. 226).
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py` —
  casi limite: articolo interamente abrogato, `text=""`, comma singolarmente
  abrogato, context popolato da `EnrichedArticle.contexts`; `context` vuoto
  se non arricchito. Il costruttore riceve `source` (non più parametro di
  chiamata); il metodo testato è `execute(article)` (non più `chunk`).
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_contextualizer.py` —
  con `Agent` fake: parsa `dict[int, str]` dal JSON canned; articolo abrogato
  → ritorna `{}` senza chiamare l'agent; JSON malformato → `ValueError`.

### Services — quiz

- `tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py` —
  `FlattenQuiz().execute(parsed_questions)`: lista vuota → lista vuota; domande
  senza sotto-domande → lista vuota; dedup sulla tripla `(text.strip(),
  correct_answer, image)` (duplicato esatto scartato, duplicato con risposta
  diversa mantenuto); `warning` loggato per ogni duplicato; denormalizzazione
  `question_id`/`topic` da `parent` verificata sui risultati.
- `tests/guidami_ai_patente_ingestor/services/quiz/test_to_embeddable_quiz.py` —
  `ToEmbeddableQuiz().execute(enriched_items)`: dedup su tripla; item unici
  mantenuti nell'ordine; delega a `QuizMapper.from_enriched_to_embeddable(item)`
  (1 argomento); lista vuota → lista vuota.
- `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py` —
  con fake `RoadSignDescriberAgent`: dedup su `(image, topic, text)` (3 sotto-domande,
  2 chiavi distinte → 2 chiamate); immagine mancante → skip + warning, nessuna
  eccezione; `execute` che lancia → skip + warning; `image_description ==
  "name. description"`; sotto-domanda con `image is None` → resta `None`;
  nessuna mutazione in place. `execute` (ex `enrich`) è il metodo testato.

> **Nota (refactor enrichment)**: `test_quiz_enrichment_service.py` non
> esiste più — `QuizEnrichmentService` rimossa. Il base-map è testato in
> `test_quiz_mapper.py` (`from_cleaned_to_enriched`); la logica di
> flatten+dedup è testata in `test_flatten_quiz.py` (service) e
> `test_to_embeddable_quiz.py` (service). `test_enrich_data_step.py` non
> esiste più (EnrichDataStep rimosso).

### Mappers — dominio (flat, non più sub-package `knowledge/` e `quiz/`)

- `tests/guidami_ai_patente_ingestor/mappers/test_article_mapper.py` —
  `from_parsed_to_enriched` copia tutti i campi comuni e imposta `contexts={}`;
  `from_embeddable_chunk_to_knowledge_chunk` copia tutti i campi (incluso
  `embedding=None` se absent); `from_enriched_to_embeddable_chunk` costruisce
  correttamente l'`EmbeddableChunkModel` con `source`, `comma_index`, `raw_text`
  e `context` estratto da `contexts`. `test_enriched_article_mapper.py` (rimosso
  in precedenza) e `tests/.../mappers/knowledge/test_article_mapper.py` (rinominato
  a flat) sono stati consolidati in questo file.
- `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper.py` —
  test per `QuizMapper` lato indexing: `from_enriched_to_embeddable(item)` (1
  argomento, modello flat — rinominato da `from_enriched_quiz_item_to_embeddable`
  in SP03; estrazione `image_filename`, `image_filename=None` se assente);
  `from_embeddable_to_quiz_question` (copia i campi persistiti, scarta
  `image_description`, mantiene `embedding`).
- `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper_flatten_at_preparation.py` —
  (SP09) `from_parsed_to_cleaned` e `from_cleaned_to_enriched` (base-map flat→flat,
  `image_description=None`). **Nessun test di dedup**: il dedup è in
  `test_flatten_quiz_step.py`.

### Mappers — agent DTO

- `tests/guidami_ai_patente_ingestor/agents/dto/test_article_contextualizer_dto.py`
  (o simile) — `ArticleContextualizerRequest` e `ArticleContextualizerResponse`
  validati come Pydantic models; campi obbligatori e tipi corretti.
- `tests/guidami_ai_patente_ingestor/agents/dto/test_road_sign_describer_dto.py`
  (o simile) — `RoadSignDescriberRequest` e `RoadSignDescriberResponse` validati.
- `tests/guidami_ai_patente_ingestor/mappers/agents/test_article_contextualizer_mapper.py` —
  `from_enriched_article_to_request` popola correttamente `title`/`text`/`paragraphs`;
  `from_response_to_enriched_article` applica `contexts` via `model_copy` senza
  mutare l'originale.
- `tests/guidami_ai_patente_ingestor/mappers/agents/test_road_sign_describer_mapper.py` —
  `from_enriched_quiz_to_request` popola `topic`/`text`; `from_response_to_enriched_quiz`
  produce `image_description = f"{name}. {description}"` via `model_copy`.

### Orchestrators — knowledge preparation flow + runner

`LoadParsedArticlesStep`/`CleanArticlesStep`/`WriteCleanedStep`/
`LoadCleanedArticlesStep`/`WriteEnrichedStep` non esistono più — sostituiti
dai generici `LoadJsonStep`/`MapStep`/`WriteJsonStep`, testati genericamente
(vedi sezione "Orchestrators — step generici" sotto). Resta domain-specific:

- `tests/guidami_ai_patente_ingestor/mappers/test_article_mapper.py` — vedi
  sezione "Mappers — dominio" sopra per il dettaglio completo.
- `tests/guidami_ai_patente_ingestor/models/knowledge/test_embeddable_chunk.py` —
  default `embedding=None`, default `context=""`, `embedded_text` senza context
  (titolo + testo uniti da `\n`), `embedded_text` con context (tre parti unite da
  `\n`), parti vuote saltate.
- `tests/guidami_ai_patente_ingestor/services/knowledge/enrichers/test_context_enricher.py` —
  con fake `ArticleContextualizerAgent`: contestualizzazione riuscita →
  `contexts` valorizzato; eccezione dell'agente → `contexts={}` + warning,
  nessuna eccezione propagata; nessuna mutazione in place (nuovi oggetti via
  `model_copy`). `test_contextualize_step.py` non esiste più (`ContextualizeStep`
  rimosso).
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` —
  (estensione SP05, stesso file di SP03) `build_knowledge_cleaning_flow`/
  `build_knowledge_enrichment_flow` ritornano un `Flow` con il nome corretto
  (`knowledge_cleaning`/`knowledge_enrichment`); source non valida →
  `ValueError`; `output_layer` non configurato → `ValueError`;
  `FlowValidator().validate(flow).required_input_keys == set()` per entrambi;
  `validate=True` non solleva.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_preparation_runner.py` —
  `run_preparation`: skip (`flow.run` non chiamato) se `out_path` esiste e
  `force=False`; esegue `flow.run()` se `out_path` non esiste; esegue
  `flow.run()` con `force=True` anche se `out_path` esiste.

### Orchestrators — step knowledge indexing

`LoadEnrichedArticlesStep` non esiste più — sostituito dal generico
`LoadJsonStep` (vedi sezione "Orchestrators — step generici" sotto).

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_chunk_articles_step.py` —
  `required == {ENRICHED_ARTICLES}`, `produced == {EMBEDDABLE_CHUNKS}`; tutti i chunk prodotti
  (repealed inclusi, nessun filtro); flatten corretto da più articoli;
  delega a `ArticleChunker.execute(article)` (non più `chunk(article, source)` —
  la source è nel costruttore del chunker, già iniettata nello step).
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_embed_chunks_step.py` —
  `required == produced == {EMBEDDABLE_CHUNKS}`; `embed_repealed=False` → i chunk repealed
  restano **presenti** con `embedding=None`; `embed_repealed=True` → tutti embeddati;
  mutazione in place + ri-scrittura stessa lista; vettori corretti; lista vuota noop.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_store_chunks_step.py` —
  `required == {CHUNK_ENTITIES}`, `produced == set()`; `execute` chiama `delete_source(source)`
  poi `bulk_insert(chunks)` nell'ordine; source iniettata passata correttamente al repository.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` —
  `build_knowledge_indexing_flow(...)` ritorna un `Flow`; `flow.name == "knowledge_indexing"`;
  source non valida → `ValueError`; `FlowValidator().validate(flow).required_input_keys == set()`;
  `validate=True` non solleva (WARNING benigno su `EMBEDDABLE_CHUNKS` di `EmbedChunksStep`);
  ordine dei 5 step verificato (`load_enriched_articles`, `chunk_articles`, `embed_chunks`,
  `map_to_chunk_entity`, `store_chunks`).
  Integrazione (`@pytest.mark.integration`): flow completo su Postgres — tutti i
  chunk inseriti (repealed inclusi), repealed con `embedding IS NULL`,
  non-repealed con vettore valorizzato.

### Orchestrators — step quiz indexing

`LoadEnrichedQuizStep`/`MapToQuizEntityStep` e `MapToEmbeddableStep` rimossi
(sostituiti rispettivamente da `LoadJsonStep`, `ApplyStep+ForEach`,
`ApplyStep(ToEmbeddableQuiz())`) — nessun test step-dedicato residuo per loro.

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py` —
  `build_quiz_indexing_flow(...)` ritorna un `Flow`; `flow.name ==
  "quiz_indexing"`; `FlowValidator().validate(flow).required_input_keys ==
  set()`; `validate=True` non solleva (WARNING benigno su `EMBEDDABLE_QUIZ`
  di `EmbedStep`); ordine dei 5 step verificato (`load_enriched_quiz`,
  `map_to_embeddable`, `embed_quiz`, `map_to_quiz_entity`, `store_quiz`).

### Orchestrators — quiz preparation: cleaning flow (SP09)

`test_flatten_quiz_step.py` non esiste più — `FlattenQuizStep` rimosso in SP04;
la logica è testata in `test_flatten_quiz.py` (service, vedi sezione "Services —
quiz" sopra).

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py` —
  `build_quiz_cleaning_flow(...)`: `Flow` con nome `"quiz_cleaning"`;
  `required_input_keys == set()`; `validate=True` non solleva; tre step
  nell'ordine `load_parsed_quiz` → `flatten_quiz` → `write_cleaned_quiz`.

### Orchestrators — quiz preparation: enrichment flow (refactor SP04)

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py` —
  `build_quiz_enrichment_flow(...)`: `Flow` con nome `"quiz_enrichment"`;
  `required_input_keys == set()`; `validate=True` non solleva; **tre step**
  nell'ordine `load_cleaned_quiz` → `enrich` → `write_enriched_quiz` (SP04
  ha unificato i precedenti `map_cleaned_to_enriched` + `enrich_quiz` in un
  unico `ApplyStep("enrich", ...)`).

> `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` e i rispettivi
> test non esistono più. `EnrichDataStep`/`MapStep` rimossi in SP04; i loro
> test (`test_enrich_data_step.py`, `test_map_step.py`) non esistono più.

### Orchestrators — step generici (SP02, esteso da SP08-bis; SP04 ha rimosso MapStep/EnrichDataStep)

- `tests/flowstep/steps/test_apply_step.py` — zero, uno, più transform; catena
  in sequenza; `get_required_keys() == {input_key}`, `get_produced_keys() ==
  {output_key}`; input_key == output_key funziona.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_embed_step.py` —
  `get_required_keys`/`get_produced_keys` identici a `{items_key}`; `execute` assegna
  embedding in place e ri-scrive la chiave nel context; `ValueError` su mismatch
  vettori/item (`zip strict`).
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_db_store_step.py` —
  `get_required_keys == {items_key}`, `get_produced_keys == set()`;
  `execute` chiama `truncate` poi `bulk_insert` nell'ordine corretto.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_store_repository.py` —
  conformità strutturale statica (pyright): `_conforms` annota `KnowledgeChunkStoreRepository`
  e `QuizQuestionStoreRepository` come `StoreRepository` senza istanziarli a runtime.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_load_json_step.py` —
  `required == set()`, `produced == {output_key}`; path risolto da `layer_resolver`.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_write_json_step.py` —
  `required == {input_key}`, `produced == set()`; scrive la lista letta dal context.

**Rimossi (SP04)**: `test_map_step.py` (MapStep rimosso), `test_enrich_data_step.py`
(EnrichDataStep rimosso).

### CLI (SP07)

- `tests/guidami_ai_patente_ingestor/test_cli.py` — 12 test unitari senza
  dipendenze esterne (tutto mockato con `unittest.mock.patch`):
  - `test_prepare_knowledge_runs_both_preparation_flows` — due factory
    chiamate + `run_preparation` invocato due volte per `prepare knowledge`.
  - `test_prepare_knowledge_passes_source_to_factories` — `source="cap"`
    propagato a `build_knowledge_cleaning_flow` e
    `build_knowledge_enrichment_flow`.
  - `test_prepare_knowledge_default_force_is_false` — `force=False` di
    default per entrambe le chiamate a `run_preparation`.
  - `test_prepare_knowledge_with_force_passes_force_true_to_runner` —
    `--force` propaga `force=True` a entrambe le chiamate a `run_preparation`.
  - `test_prepare_knowledge_requires_source_argument` — `SystemExit` se
    `--source` assente.
  - `test_index_knowledge_builds_flow_with_source_and_runs` — factory
    riceve `source="cds"` e `flow.run()` chiamato una volta.
  - `test_index_knowledge_requires_source_argument` — `SystemExit` se
    `--source` assente.
  - `test_prepare_quiz_runs_both_preparation_flows` — due factory chiamate
    + `run_preparation` invocato due volte per `prepare quiz`.
  - `test_prepare_quiz_with_force_passes_force_true_to_runner` — `--force`
    propaga `force=True`.
  - `test_index_quiz_builds_flow_and_runs` — factory chiamata una volta e
    `flow.run()` invocato.
  - `test_reset_knowledge_calls_knowledge_chunk_truncate` — `truncate()`
    invocato su `KnowledgeChunkStoreRepository`.
  - `test_reset_quiz_calls_quiz_question_truncate` — `truncate()` invocato
    su `QuizQuestionStoreRepository`.

> Tutti i test usano `monkeypatch.setattr(sys, "argv", [...])` per simulare
> gli argomenti CLI e patching a livello di modulo per isolare le dipendenze.

### Infrastruttura condivisa

- `tests/commons/clients/test_postgres_client.py` — aggiornato per
  `PostgresConnectionConfig`; nessuna assert su `similarity_search` (rimosso).
- **Non ancora implementato**: test di integrazione end-to-end con marker
  `@pytest.mark.integration` dedicato.
