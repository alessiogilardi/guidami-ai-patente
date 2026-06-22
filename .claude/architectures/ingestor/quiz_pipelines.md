# Ingestor — Pipeline quiz bank

Riferimento progettazione: `plans/architecture-quiz-bank.md`,
`plans/ingest--data-preparation.md`.

Vedi [data_preparation.md](data_preparation.md) per `QuizDataPreparationPipeline`
(stadio di enrichment vision che produce il layer `enriched`).
Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`,
`LayerResolver` e gli entry point CLI.

## Decisioni implementate

### `entities/quiz_bank.py` — `QuizMainQuestion` / `QuizSubQuestion`

- Mappano 1:1 il JSON sorgente `data/parsed/quiz-patente-ab/quiz-patente-ab.json`
  (715 domande madri, 7106 sotto-domande): `QuizMainQuestion` (`question_id:
  int`, `topic: str`, `sub_questions: list[QuizSubQuestion]`),
  `QuizSubQuestion` (`number: str`, `text: str`, `correct_answer: bool`,
  `image: str | None = None`).
- `question_id` è una stringa numerica nel JSON, ma Pydantic v2 la coercise a
  `int` (coercizione lax) — la colonna `quiz_questions.question_id INTEGER`
  è quindi corretta senza conversioni manuali.

Per la struttura `db/`/`json/` e la base class `JsonRepository[T]` vedi
[knowledge_pipelines.md](knowledge_pipelines.md).

### `repositories/json/quiz_bank_repository.py` — `QuizBankRepository`

- Estende `JsonRepository[QuizMainQuestion]`; eredita `load` e `write` da
  base. In pratica usato solo in lettura (`load`): non c'è uno stadio
  "cleaned" per il quiz bank. Nessuna dipendenza/config iniettata.
  Re-esportato da `repositories/__init__.py`.

### `services/quiz/quiz_question_mapper.py` — `QuizQuestionMapper`

- **Input aggiornato**: ora accetta `list[EnrichedQuizMainQuestion]` (layer
  enriched) invece di `list[QuizMainQuestion]` (layer parsed).
- `map(main_questions: list[EnrichedQuizMainQuestion]) ->
  list[EmbeddableQuizQuestion]`: appiattisce ogni `sub_questions` in una
  `EmbeddableQuizQuestion`, denormalizzando `question_id`/`topic` dalla
  domanda madre e portando `image_description` dalla sotto-domanda arricchita.
- **Output aggiornato**: produce `EmbeddableQuizQuestion` (non più
  `QuizQuestion` direttamente). La conversione finale in entità DB
  (`QuizQuestion`) è delegata a `EmbeddableQuizQuestionMapper.to_entity()`.
- `image_filename = PurePosixPath(image).name if image is not None else
  None` — salva solo il nome file (invariato).
- **Dedup duplicati esatti**: chiave `(text.strip(), correct_answer, image)`
  in un `set`; ogni duplicato scartato genera
  `logger.warning(...)`. Verificato su dati reali: 8 duplicati esatti su
  7106 sotto-domande → 7098 righe mappate.

### `mappers/quiz/embeddable_quiz_question_mapper.py` — `EmbeddableQuizQuestionMapper`

- `to_entity(question: EmbeddableQuizQuestion) -> QuizQuestion`: copia i
  campi persistiti (`number`, `question_id`, `topic`, `text`,
  `correct_answer`, `image_filename`, `embedding`), **scarta**
  `image_description` (non è una colonna di `quiz_questions`). Mapper
  stateless, nessuna config iniettata. Applicato in
  `QuizIndexingPipeline._assign_embeddings` per ottenere le entità da
  passare al repository.

### `orchestrators/steps/quiz/` — step di dominio quiz (SP04)

Tre step flowstep domain-specific per il quiz indexing. Vivono in
`orchestrators/steps/quiz/`, mai in `services/` (colla di orchestrazione, non
logica di dominio). Delegano ai mapper statici esistenti in `mappers/quiz/`.

- **`LoadEnrichedQuizStep`**: iniettati `name`, `enriched_quiz_bank_repository`,
  `layer_resolver`, `input_layer: str`, `source: str`.
  `execute`: chiama `layer_resolver.path(input_layer, source)` +
  `repository.load(path)` → `put(ENRICHED_QUIZ, list[EnrichedQuizMainQuestion])`.
  `required=set()`, `produced={ENRICHED_QUIZ}`. La `source` è iniettata (no
  hardcode `"quiz"`), speculare a `LoadEnrichedArticlesStep` (SP03).
- **`MapToEmbeddableStep`**: nessuna iniezione di config. `execute`: legge
  `ENRICHED_QUIZ`, delega `QuizQuestionMapper.from_enriched_quiz_main_questions_to_embeddable_quiz_questions`
  (dedup interna: 8 duplicati esatti su 7106 sotto-domande → 7098 righe).
  `required={ENRICHED_QUIZ}`, `produced={EMBEDDABLE_QUIZ}`.
- **`MapToQuizEntityStep`**: nessuna iniezione di config. `execute`: legge
  `EMBEDDABLE_QUIZ`, delega `EmbeddableQuizQuestionMapper.to_entity` per ogni
  elemento. `required={EMBEDDABLE_QUIZ}`, `produced={QUIZ_ENTITIES}`.

Il package `orchestrators/steps/quiz/__init__.py` re-esporta i tre step.

### `orchestrators/quiz_flows.py` — flow factory quiz (SP04)

```python
def build_quiz_indexing_flow(
    config: IngestorConfig,
    layer_resolver: LayerResolver,
    embedding_client: EmbeddingClient,
    postgres_client: PostgresClient,
    validate: bool = False,
) -> Flow
```

Catena: `LoadEnrichedQuizStep` → `MapToEmbeddableStep` →
`EmbedStep(items_key=EMBEDDABLE_QUIZ)` → `MapToQuizEntityStep` →
`DbStoreStep(items_key=QUIZ_ENTITIES)`.

Re-esportata da `orchestrators/__init__.py` accanto a
`build_knowledge_indexing_flow`.

**Decisioni:**

- `source` derivata da `config.quiz_indexing.sources[0]`: il quiz bank ha
  sempre una sola source (`"quiz"`), quindi non c'è parametro `source` esplicito
  come nel knowledge flow (che è per-source).
- `input_layer` letto da `config.quiz_indexing.input_layer`.
- **`DbStoreStep` generico (truncate full-reload)** al posto di uno step
  custom delete-by-source: il quiz ha una sola source, quindi il
  `TRUNCATE TABLE quiz_questions` è corretto e sicuro. Divergenza voluta dal
  `StoreChunksStep` di SP03 (delete-by-source) che serve perché le due source
  knowledge (`cds`, `cap`) coesistono nella stessa tabella.
- **`EmbedStep` generico riusato** (con `items_key=EMBEDDABLE_QUIZ`): il quiz
  non ha il filtro `embed_repealed`, quindi lo step generico è sufficiente senza
  un dedicato `EmbedQuizStep`. Il WARNING benigno del `FlowValidator`
  "Produced key overwrites an already available key" (perché `required == produced
  == {EMBEDDABLE_QUIZ}`) non è un ERROR e non blocca `build(validate=True)`.
- `QuizQuestionStoreRepository` soddisfa strutturalmente il `StoreRepository`
  Protocol (già verificato in `test_store_repository.py`): `DbStoreStep` può
  riceverlo senza modifiche.

**Cutover CLI pendente (SP07):** il flow non è ancora wired a un entry point
CLI. Lo script `ingest-quiz` e `reset_quiz_db.py` restano nella configurazione
corrente fino a SP07.

### `repositories/db/` — `QuizQuestionStoreRepository`

- Sostituisce l'uso diretto di `VectorStoreClient` (rimosso, vedi
  `commons.md`): repository di scrittura full-reload, iniettato con un
  `PostgresClient` generico e il nome tabella
  (`config.quiz_questions_table`). Vive in `repositories/db/` (storage
  Postgres), re-esportato da `repositories/__init__.py`.
- `truncate()` + `bulk_insert(questions: list[QuizQuestion])` — colonne
  `number, question_id, topic, text, correct_answer, image_filename,
  embedding`.
- Costruisce la query con `psycopg.sql.SQL(...).format(table=
  sql.Identifier(table_name))` e `client.execute_many(query, params_seq)`;
  `bulk_insert` ritorna immediatamente (`return`) se la lista è vuota.
