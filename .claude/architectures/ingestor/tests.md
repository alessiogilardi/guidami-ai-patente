# Ingestor — Test

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`, `plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/05-knowledge-preparation-flow.md`.

## Test

### Repositories

- `tests/guidami_ai_patente_ingestor/repositories/test_article_repository.py` —
  `load`/`write` round-trip su fixture reali.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  round-trip `write`/`load` su `EnrichedArticle` con `contexts`.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_quiz_bank_repository.py` —
  round-trip `write`/`load` su `EnrichedQuizMainQuestion` con
  `image_description`.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_bank_repository.py` —
  `load` su fixture reale (`tests/.../fixtures/quiz_bank_sample.json`):
  mappatura in `QuizMainQuestion`/`QuizSubQuestion`.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_question_store_repository.py` —
  contro il Postgres del compose (no marker `integration`): `truncate` +
  `bulk_insert` su `quiz_questions` con colonna `embedding`.

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
  se non arricchito.
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_contextualizer.py` —
  con `Agent` fake: parsa `dict[int, str]` dal JSON canned; articolo abrogato
  → ritorna `{}` senza chiamare l'agent; JSON malformato → `ValueError`.

### Services — quiz

- `tests/guidami_ai_patente_ingestor/services/quiz/test_quiz_question_mapper.py` —
  accetta `EnrichedQuizMainQuestion`; produce `EmbeddableQuizQuestion` con
  `image_description`; denormalizzazione `question_id`/`topic`; estrazione
  `image_filename`; `image_filename=None` se assente; dedup su
  `(text.strip(), correct_answer, image)`.
- `tests/guidami_ai_patente_ingestor/services/quiz/test_road_sign_describer.py` —
  con `Agent` fake: parsa `ImageDescription` dal JSON canned; JSON malformato
  → `ValueError`.

### Mappers

- `tests/guidami_ai_patente_ingestor/mappers/quiz/test_embeddable_quiz_question_mapper.py` —
  `to_entity` copia i campi persistiti, scarta `image_description`, mantiene
  `embedding`.

### Orchestrators — preparation

- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_preparation/test_quiz_data_preparation_pipeline.py` —
  unit con `Mock`: solo i filename unici descritti; enriched bank con
  `image_description` inline; immagine mancante → warning + `None`;
  `force=True`.
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_preparation/test_quiz_data_preparation_pipeline_builder.py` —
  path enriched mancante → `FileNotFoundError`.

### Orchestrators — knowledge preparation flow + runner (SP05)

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_load_parsed_articles_step.py` —
  `required == set()`, `produced == {PARSED_ARTICLES}`; `execute` carica la
  source iniettata via `layer_resolver.path(input_layer, source)`; source
  diversa produce lista distinta.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_clean_articles_step.py` —
  `required == {PARSED_ARTICLES}`, `produced == {CLEANED_ARTICLES}`; delega a
  `ArticleCleaner.clean` per ogni articolo.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_write_cleaned_step.py` —
  `required == {CLEANED_ARTICLES}`, `produced == set()`; `execute` risolve il
  path sul layer `cleaned` e chiama `ArticleRepository.write`.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_load_cleaned_articles_step.py` —
  `required == set()`, `produced == {CLEANED_ARTICLES}`; carica dal layer
  `cleaned` iniettato.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_contextualize_step.py` —
  `required == {CLEANED_ARTICLES}`, `produced == {ENRICHED_ARTICLES}`; delega
  `ArticleContextualizerAgent.contextualize` + `EnrichedArticleMapper` per ogni
  articolo.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_write_enriched_step.py` —
  `required == {ENRICHED_ARTICLES}`, `produced == set()`; `execute` risolve il
  path sul layer `enriched` e chiama `EnrichedArticleRepository.write`.
- `tests/guidami_ai_patente_ingestor/mappers/knowledge/test_enriched_article_mapper.py` —
  `from_article_to_enriched_article` copia tutti i campi comuni e imposta
  `contexts`.
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

### Orchestrators — step knowledge (SP03)

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_load_enriched_articles_step.py` —
  `required == set()`, `produced == {ENRICHED_ARTICLES}`; `execute` carica la
  source iniettata e produce la lista piatta; source diversa produce lista distinta.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_chunk_articles_step.py` —
  `required == {ENRICHED_ARTICLES}`, `produced == {CHUNKS}`; tutti i chunk prodotti
  (repealed inclusi, nessun filtro); flatten corretto da più articoli;
  deleghe a `ArticleChunker` con la source iniettata nel costruttore.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_embed_chunks_step.py` —
  `required == produced == {CHUNKS}`; `embed_repealed=False` → i chunk repealed
  restano **presenti** con `embedding=None`; `embed_repealed=True` → tutti embeddati;
  mutazione in place + ri-scrittura stessa lista; vettori corretti; lista vuota noop.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_store_chunks_step.py` —
  `required == {CHUNKS}`, `produced == set()`; `execute` chiama `delete_source(source)`
  poi `bulk_insert(chunks)` nell'ordine; source iniettata passata correttamente al repository.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` —
  `build_knowledge_indexing_flow(...)` ritorna un `Flow`; `flow.name == "knowledge_indexing"`;
  source non valida → `ValueError`; `FlowValidator().validate(flow).required_input_keys == set()`;
  `validate=True` non solleva (WARNING benigno su `CHUNKS` di `EmbedChunksStep`).
  Integrazione (`@pytest.mark.integration`): flow completo su Postgres — tutti i
  chunk inseriti (repealed inclusi), repealed con `embedding IS NULL`,
  non-repealed con vettore valorizzato.

### Orchestrators — step quiz (SP04)

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/quiz/test_load_enriched_quiz_step.py` —
  `required == set()`, `produced == {ENRICHED_QUIZ}`; `execute` carica via
  `layer_resolver.path(input_layer, source)` e repository; source iniettata
  (non hardcoded `"quiz"`); source diversa produce lista distinta.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/quiz/test_map_to_embeddable_step.py` —
  `required == {ENRICHED_QUIZ}`, `produced == {EMBEDDABLE_QUIZ}`; delega
  `QuizQuestionMapper`; dedup sui duplicati esatti.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/quiz/test_map_to_quiz_entity_step.py` —
  `required == {EMBEDDABLE_QUIZ}`, `produced == {QUIZ_ENTITIES}`; delega
  `EmbeddableQuizQuestionMapper.to_entity`; contratto chiavi rispettato.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py` —
  `build_quiz_indexing_flow(...)` ritorna un `Flow`; `flow.name ==
  "quiz_indexing"`; `FlowValidator().validate(flow).required_input_keys ==
  set()`; `validate=True` non solleva (WARNING benigno su `EMBEDDABLE_QUIZ`
  di `EmbedStep`); ordine dei 5 step verificato.

### Orchestrators — step generici (SP02)

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_embed_step.py` —
  `get_required_keys`/`get_produced_keys` identici a `{items_key}`; `execute` assegna
  embedding in place e ri-scrive la chiave nel context; `ValueError` su mismatch
  vettori/item (`zip strict`). Fake: `_FakeClient` (ritorna `[len(text)]`),
  `_FakeEmbeddable` (soddisfa `Embedded`), stub `EmbeddingService` che ritorna
  un vettore in meno.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_db_store_step.py` —
  `get_required_keys == {items_key}`, `get_produced_keys == set()`;
  `execute` chiama `truncate` poi `bulk_insert` nell'ordine, con gli item corretti.
  Fake: `_RecordingRepo` (soddisfa `StoreRepository`, registra eventi).
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_store_repository.py` —
  conformità strutturale statica (pyright): `_conforms` annota `KnowledgeChunkStoreRepository`
  e `QuizQuestionStoreRepository` come `StoreRepository` senza istanziarli a runtime
  (nessun Postgres necessario).

### Infrastruttura condivisa

- `tests/commons/clients/test_postgres_client.py` — aggiornato per
  `PostgresConnectionConfig`; nessuna assert su `similarity_search` (rimosso).
- **Non ancora implementato**: test di integrazione end-to-end con marker
  `@pytest.mark.integration` dedicato.
