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

### `orchestrators/quiz_indexing/` — `QuizIndexingPipeline` (rimosso)

`QuizIndexingPipeline`, `QuizIndexingPipelineBuilder` e l'entry point
`quiz_main.py` sono stati rimossi in SP03-bis. Il flow di quiz indexing sarà
reintrodotto come flow flowstep in SP04. Lo script `ingest-quiz` non è
disponibile fino ad allora.

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
