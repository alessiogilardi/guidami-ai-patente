# Ingestor — Tests

## Tests

### Repositories

- `tests/guidami_ai_patente_ingestor/repositories/test_article_repository.py` —
  `load`/`write` round-trip on real fixtures.
- `tests/guidami_ai_patente_ingestor/repositories/test_enriched_article_repository.py` —
  `write`/`load` round-trip on `EnrichedArticle` with `contexts`.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_question_store_repository.py` —
  all tests marked `@pytest.mark.integration` (require the compose Postgres):
  `truncate` + `bulk_insert` on `quiz_questions` with `embedding` column.

> **Note (`BulkInsertStoreRepository` refactor)**: `QuizQuestionStoreRepository`
> and `KnowledgeChunkStoreRepository` now share the generic base
> `BulkInsertStoreRepository[T]` (see
> [knowledge_pipelines.md](knowledge_pipelines.md)) for `truncate`/`bulk_insert`.
> There is no dedicated unit test for the base itself (it is abstract, `_` prefix,
> not re-exported): coverage comes only from integration tests on the two concrete
> subclasses (`test_quiz_question_store_repository.py` above; the knowledge store
> is covered via `test_knowledge_flows.py`, see the "Orchestrators — knowledge
> indexing steps" section below).

> **Note (SP09)**: `test_quiz_bank_repository.py` and
> `test_enriched_quiz_bank_repository.py` no longer exist — the quiz
> preparation flows now use generic `LoadJsonStep`/`WriteJsonStep`
> (parameterised with `model_class`), not `QuizBankRepository`/
> `EnrichedQuizBankRepository` directly in the flows. The two repositories
> remain in the code (`repositories/json/`) but without a current dedicated test.

### Config and layer resolver

- `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  `layers`/`sources`/selectors structure; `postgres: PostgresConnectionConfig`
  required (`ValidationError` if absent with `_env_file=None`);
  immutability (`frozen=True`).
- `tests/guidami_ai_patente_ingestor/services/test_layer_resolver.py` —
  `path(layer, source)` composes correctly; unknown layer/source → error.

### Services — knowledge

- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_cleaner.py` —
  on real fixtures (`tests/.../fixtures/cds_sample.json`, `cap_sample.json`):
  inline markup removal, ordinal removal, standalone markers, title wrapped in
  parentheses, duplicate ordinal (art. 226).
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py` —
  edge cases: fully repealed article, `text=""`, single repealed clause,
  context populated from `EnrichedArticle.contexts`; empty `context`
  if not enriched. Constructor receives `source` (no longer a call parameter);
  the tested method is `execute(article)` (no longer `chunk`).
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_contextualizer.py` —
  with fake `Agent`: parses `dict[int, str]` from canned JSON; repealed article
  → returns `{}` without calling the agent; malformed JSON → `ValueError`.

### Services — quiz

- `tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py` —
  `FlattenQuiz().execute(parsed_questions)`: empty list → empty list; questions
  without sub-questions → empty list; dedup on triple `(text.strip(),
  correct_answer, image)` (exact duplicate discarded, duplicate with different
  answer kept); `warning` logged for each duplicate; `question_id`/`topic`
  denormalisation from `parent` verified on results.
- `tests/guidami_ai_patente_ingestor/services/quiz/test_to_embeddable_quiz.py` —
  `ToEmbeddableQuiz().execute(enriched_items)`: dedup on triple; unique items
  kept in order; delegation to `QuizMapper.from_enriched_to_embeddable(item)`
  (1 argument); empty list → empty list.
- `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py` —
  with fake `RoadSignDescriberAgent`: dedup on `(image, topic, text)` (3 sub-questions,
  2 distinct keys → 2 calls); missing image → skip + warning, no exception;
  `execute` raising → skip + warning; `image_description ==
  "name. description"`; sub-question with `image is None` → stays `None`;
  no in-place mutation. `execute` (ex `enrich`) is the tested method.

> **Note (enrichment refactor)**: `test_quiz_enrichment_service.py` no
> longer exists — `QuizEnrichmentService` removed. The base-map is tested in
> `test_quiz_mapper.py` (`from_cleaned_to_enriched`); the flatten+dedup logic
> is tested in `test_flatten_quiz.py` (service) and
> `test_to_embeddable_quiz.py` (service). `test_enrich_data_step.py` no
> longer exists (EnrichDataStep removed).

### Mappers — domain (flat, no longer in `knowledge/` and `quiz/` sub-packages)

- `tests/guidami_ai_patente_ingestor/mappers/test_article_mapper.py` —
  `from_parsed_to_enriched` copies all common fields and sets `contexts={}`;
  `from_embeddable_chunk_to_knowledge_chunk` copies all fields (including
  `embedding=None` if absent); `from_enriched_to_embeddable_chunk` correctly
  builds the `EmbeddableChunkModel` with `source`, `comma_index`, `raw_text`
  and `context` extracted from `contexts`. `test_enriched_article_mapper.py` (removed
  earlier) and `tests/.../mappers/knowledge/test_article_mapper.py` (renamed
  to flat) have been consolidated into this file.
- `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper.py` —
  tests for `QuizMapper` on the indexing side: `from_enriched_to_embeddable(item)` (1
  argument, flat model — renamed from `from_enriched_quiz_item_to_embeddable`
  in SP03; `image_filename` extraction, `image_filename=None` if absent);
  `from_embeddable_to_quiz_question` (copies persisted fields, drops
  `image_description`, keeps `embedding`).
- `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper_flatten_at_preparation.py` —
  (SP09) `from_parsed_to_cleaned` and `from_cleaned_to_enriched` (base-map flat→flat,
  `image_description=None`). **No dedup test**: dedup is in
  `test_flatten_quiz_step.py`.

### Mappers — agent DTOs

- `tests/guidami_ai_patente_ingestor/agents/dto/test_article_contextualizer_dto.py`
  (or similar) — `ArticleContextualizerRequest` and `ArticleContextualizerResponse`
  validated as Pydantic models; required fields and correct types.
- `tests/guidami_ai_patente_ingestor/agents/dto/test_road_sign_describer_dto.py`
  (or similar) — `RoadSignDescriberRequest` and `RoadSignDescriberResponse` validated.
- `tests/guidami_ai_patente_ingestor/mappers/agents/test_article_contextualizer_mapper.py` —
  `from_enriched_article_to_request` correctly populates `title`/`text`/`paragraphs`;
  `from_response_to_enriched_article` applies `contexts` via `model_copy` without
  mutating the original.
- `tests/guidami_ai_patente_ingestor/mappers/agents/test_road_sign_describer_mapper.py` —
  `from_enriched_quiz_to_request` populates `topic`/`text`; `from_response_to_enriched_quiz`
  produces `image_description = f"{name}. {description}"` via `model_copy`.

### Orchestrators — knowledge preparation flow + runner

`LoadParsedArticlesStep`/`CleanArticlesStep`/`WriteCleanedStep`/
`LoadCleanedArticlesStep`/`WriteEnrichedStep` no longer exist — replaced by
generic `LoadJsonStep`/`MapStep`/`WriteJsonStep`, tested generically
(see "Orchestrators — generic steps" section below). Remaining domain-specific:

- `tests/guidami_ai_patente_ingestor/mappers/test_article_mapper.py` — see
  "Mappers — domain" section above for full detail.
- `tests/guidami_ai_patente_ingestor/models/knowledge/test_embeddable_chunk.py` —
  default `embedding=None`, default `context=""`, `embedded_text` without context
  (title + text joined by `\n`), `embedded_text` with context (three parts joined by
  `\n`), empty parts skipped.
- `tests/guidami_ai_patente_ingestor/services/knowledge/enrichers/test_context_enricher.py` —
  with fake `ArticleContextualizerAgent`: successful contextualization →
  `contexts` populated; agent exception → `contexts={}` + warning,
  no exception propagated; no in-place mutation (new objects via
  `model_copy`). `test_contextualize_step.py` no longer exists (`ContextualizeStep`
  removed).
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` —
  (SP05 extension, same file as SP03) `build_knowledge_cleaning_flow`/
  `build_knowledge_enrichment_flow` return a `Flow` with the correct name
  (`knowledge_cleaning`/`knowledge_enrichment`); invalid source →
  `ValueError`; `output_layer` not configured → `ValueError`;
  `FlowValidator().validate(flow).required_input_keys == set()` for both;
  `validate=True` does not raise.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_preparation_runner.py` —
  `run_preparation`: skip (`flow.run` not called) if `out_path` exists and
  `force=False`; executes `flow.run()` if `out_path` does not exist; executes
  `flow.run()` with `force=True` even if `out_path` exists.

### Orchestrators — knowledge indexing steps

`LoadEnrichedArticlesStep` no longer exists — replaced by the generic
`LoadJsonStep` (see "Orchestrators — generic steps" section below).

- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_chunk_articles_step.py` —
  `required == {ENRICHED_ARTICLES}`, `produced == {EMBEDDABLE_CHUNKS}`; all produced chunks
  (repealed included, no filter); correct flatten from multiple articles;
  delegation to `ArticleChunker.execute(article)` (no longer `chunk(article, source)` —
  source is in the chunker's constructor, already injected into the step).
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_embed_chunks_step.py` —
  `required == produced == {EMBEDDABLE_CHUNKS}`; `embed_repealed=False` → repealed chunks
  remain **present** with `embedding=None`; `embed_repealed=True` → all embedded;
  in-place mutation + rewrite of same list; correct vectors; empty list noop.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_store_chunks_step.py` —
  `required == {CHUNK_ENTITIES}`, `produced == set()`; `execute` calls `delete_source(source)`
  then `bulk_insert(chunks)` in order; injected source passed correctly to the repository.
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` —
  `build_knowledge_indexing_flow(...)` returns a `Flow`; `flow.name == "knowledge_indexing"`;
  invalid source → `ValueError`; `FlowValidator().validate(flow).required_input_keys == set()`;
  `validate=True` does not raise (benign WARNING on `EMBEDDABLE_CHUNKS` from `EmbedChunksStep`);
  order of the 5 steps verified (`load_enriched_articles`, `chunk_articles`, `embed_chunks`,
  `map_to_chunk_entity`, `store_chunks`).
  Integration (`@pytest.mark.integration`): full flow on Postgres — all chunks inserted
  (repealed included), repealed with `embedding IS NULL`,
  non-repealed with vector populated.

### Orchestrators — quiz indexing steps

`LoadEnrichedQuizStep`/`MapToQuizEntityStep` and `MapToEmbeddableStep` removed
(replaced respectively by `LoadJsonStep`, `ApplyStep+ForEach`,
`ApplyStep(ToEmbeddableQuiz())`) — no remaining dedicated step tests for them.

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py` —
  `build_quiz_indexing_flow(...)` returns a `Flow`; `flow.name ==
  "quiz_indexing"`; `FlowValidator().validate(flow).required_input_keys ==
  set()`; `validate=True` does not raise (benign WARNING on `EMBEDDABLE_QUIZ`
  from `EmbedStep`); order of the 5 steps verified (`load_enriched_quiz`,
  `map_to_embeddable`, `embed_quiz`, `map_to_quiz_entity`, `store_quiz`).

### Orchestrators — quiz preparation: cleaning flow (SP09)

`test_flatten_quiz_step.py` no longer exists — `FlattenQuizStep` removed in SP04;
the logic is tested in `test_flatten_quiz.py` (service, see "Services —
quiz" section above).

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py` —
  `build_quiz_cleaning_flow(...)`: `Flow` with name `"quiz_cleaning"`;
  `required_input_keys == set()`; `validate=True` does not raise; three steps
  in order `load_parsed_quiz` → `flatten_quiz` → `write_cleaned_quiz`.

### Orchestrators — quiz preparation: enrichment flow (SP04 refactor)

- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py` —
  `build_quiz_enrichment_flow(...)`: `Flow` with name `"quiz_enrichment"`;
  `required_input_keys == set()`; `validate=True` does not raise; **three steps**
  in order `load_cleaned_quiz` → `enrich` → `write_enriched_quiz` (SP04
  unified the previous `map_cleaned_to_enriched` + `enrich_quiz` into a
  single `ApplyStep("enrich", ...)`).

> `LoadQuizStep`, `EnrichQuizStep`, `WriteEnrichedQuizStep` and their respective
> tests no longer exist. `EnrichDataStep`/`MapStep` removed in SP04; their
> tests (`test_enrich_data_step.py`, `test_map_step.py`) no longer exist.

### Orchestrators — generic steps (SP02, extended by SP08-bis; SP04 removed MapStep/EnrichDataStep)

- `tests/flowstep/steps/test_apply_step.py` — zero, one, multiple transforms; chain
  in sequence; `get_required_keys() == {input_key}`, `get_produced_keys() ==
  {output_key}`; input_key == output_key works.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_embed_step.py` —
  `get_required_keys`/`get_produced_keys` both equal to `{items_key}`; `execute` assigns
  embedding in place and rewrites the key in the context; `ValueError` on
  vector/item mismatch (`zip strict`).
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_db_store_step.py` —
  `get_required_keys == {items_key}`, `get_produced_keys == set()`;
  `execute` calls `truncate` then `bulk_insert` in the correct order.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_store_repository.py` —
  static structural conformance (pyright): `_conforms` annotates `KnowledgeChunkStoreRepository`
  and `QuizQuestionStoreRepository` as `StoreRepository` without instantiating them at runtime.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_load_json_step.py` —
  `required == set()`, `produced == {output_key}`; path resolved by `layer_resolver`.
- `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_write_json_step.py` —
  `required == {input_key}`, `produced == set()`; writes the list read from the context.

**Removed (SP04)**: `test_map_step.py` (MapStep removed), `test_enrich_data_step.py`
(EnrichDataStep removed).

### CLI (SP07)

- `tests/guidami_ai_patente_ingestor/test_cli.py` — 12 unit tests with no
  external dependencies (everything mocked with `unittest.mock.patch`):
  - `test_prepare_knowledge_runs_both_preparation_flows` — two factory
    calls + `run_preparation` invoked twice for `prepare knowledge`.
  - `test_prepare_knowledge_passes_source_to_factories` — `source="cap"`
    propagated to `build_knowledge_cleaning_flow` and
    `build_knowledge_enrichment_flow`.
  - `test_prepare_knowledge_default_force_is_false` — `force=False` by
    default for both calls to `run_preparation`.
  - `test_prepare_knowledge_with_force_passes_force_true_to_runner` —
    `--force` propagates `force=True` to both calls to `run_preparation`.
  - `test_prepare_knowledge_requires_source_argument` — `SystemExit` if
    `--source` is absent.
  - `test_index_knowledge_builds_flow_with_source_and_runs` — factory
    receives `source="cds"` and `flow.run()` called once.
  - `test_index_knowledge_requires_source_argument` — `SystemExit` if
    `--source` is absent.
  - `test_prepare_quiz_runs_both_preparation_flows` — two factory calls
    + `run_preparation` invoked twice for `prepare quiz`.
  - `test_prepare_quiz_with_force_passes_force_true_to_runner` — `--force`
    propagates `force=True`.
  - `test_index_quiz_builds_flow_and_runs` — factory called once and
    `flow.run()` invoked.
  - `test_reset_knowledge_calls_knowledge_chunk_truncate` — `truncate()`
    invoked on `KnowledgeChunkStoreRepository`.
  - `test_reset_quiz_calls_quiz_question_truncate` — `truncate()` invoked
    on `QuizQuestionStoreRepository`.

> All tests use `monkeypatch.setattr(sys, "argv", [...])` to simulate
> CLI arguments and module-level patching to isolate dependencies.

### Shared infrastructure

- `tests/commons/clients/test_postgres_client.py` — updated for
  `PostgresConnectionConfig`; no assert on `similarity_search` (removed).
- **Not yet implemented**: end-to-end integration tests with dedicated
  `@pytest.mark.integration` marker.
