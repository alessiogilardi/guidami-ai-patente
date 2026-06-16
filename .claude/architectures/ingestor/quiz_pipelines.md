# Ingestor — Pipeline quiz bank

Riferimento progettazione: `plans/architecture-quiz-bank.md`.

Vedi [config_and_entrypoints.md](config_and_entrypoints.md) per `IngestorConfig`
e gli entry point CLI.

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

### `repositories/quiz_bank_repository.py` — `QuizBankRepository`

- `load(path: Path) -> list[QuizMainQuestion]`: legge il JSON e valida ogni
  elemento con `QuizMainQuestion.model_validate`. Nessuna dipendenza/config
  iniettata — stesso ruolo di `ArticleRepository` per il quiz bank, ma solo
  lettura (non c'è uno stadio "cleaned" per il quiz bank).

### `services/quiz/quiz_question_mapper.py` — `QuizQuestionMapper`

- `map(main_questions: list[QuizMainQuestion]) -> list[QuizQuestion]`:
  appiattisce ogni `sub_questions` in una `QuizQuestion`, denormalizzando
  `question_id`/`topic` dalla domanda madre.
- `image_filename = PurePosixPath(image).name if image is not None else
  None` — salva solo il nome file (non il path repo-relative stantio della
  fonte), risolvendo l'incoerenza `data/processed` vs `data/parsed` osservata
  nei dati senza dipendere da un refactor del parser (decisione 4 del piano).
- **Dedup duplicati esatti**: chiave `(text.strip(), correct_answer, image)`
  in un `set`; ogni duplicato scartato genera
  `logger.warning(f"skipping duplicate sub-question {number} (question_id=...)")`.
  Verificato su dati reali: 8 duplicati esatti su 7106 sotto-domande → 7098
  righe mappate.

### `orchestrators/quiz_indexing/` — `QuizIndexingPipeline` + `QuizIndexingPipelineBuilder`

- **`QuizIndexingPipeline.run()`** — quattro step lineari:
  1. `QuizBankRepository.load(config.quiz_bank_path)`;
  2. `QuizQuestionMapper.map(main_questions)`;
  3. `_assign_embeddings(questions)`: batch di `config.embedding_batch_size`,
     `EmbeddingClient.embed_passages([q.embedded_text for q in batch])`
     (il testo embeddato è `f"{topic} {text}"`, topic prefissato),
     assegnazione `question.embedding = vector` in-place (campo mutabile).
     Stessa strategia di `_assign_embeddings` in `IndexingPipeline`.
  4. `QuizQuestionStoreRepository.truncate()` poi `bulk_insert(questions)`
     (full reload, stessa strategia di `IndexingPipeline`).
  - Dipendenze iniettate via costruttore: `QuizBankRepository`,
    `QuizQuestionMapper`, `QuizQuestionStoreRepository`,
    `EmbeddingClient` (ABC), `IngestorConfig`.
- **`QuizIndexingPipelineBuilder`**: valida l'esistenza di
  `config.quiz_bank_path` con `FileNotFoundError` fail-fast prima di
  istanziare il client di embedding o `PostgresClient`. Setter fluent
  `with_quiz_bank_repository`, `with_quiz_question_mapper`,
  `with_quiz_question_store_repository`, `with_embedding_client`
  (ritornano `Self`); `build()` usa controlli espliciti `is not None`,
  stesso pattern di `IndexingPipelineBuilder`. Default di
  `embedding_client`: `LiteLLMEmbeddingClient(config.embedding)` (cloud,
  `text-embedding-3-small` via OpenRouter) — stesso default di
  `IndexingPipelineBuilder`, per garantire che corpus e quiz siano
  embedati nello stesso spazio vettoriale. Default di
  `quiz_question_store_repository`:
  `QuizQuestionStoreRepository(PostgresClient(config.postgres),
  config.quiz_questions_table)`.

### `repositories/` — `QuizQuestionStoreRepository`

- Sostituisce l'uso diretto di `VectorStoreClient` (rimosso, vedi
  `commons.md`): repository di scrittura full-reload, iniettato con un
  `PostgresClient` generico e il nome tabella
  (`config.quiz_questions_table`).
- `truncate()` + `bulk_insert(questions: list[QuizQuestion])` — colonne
  `number, question_id, topic, text, correct_answer, image_filename,
  embedding`.
- Costruisce la query con `psycopg.sql.SQL(...).format(table=
  sql.Identifier(table_name))` e `client.execute_many(query, params_seq)`;
  `bulk_insert` ritorna immediatamente (`return`) se la lista è vuota.
