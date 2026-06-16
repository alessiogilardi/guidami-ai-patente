# Ingestor — Test

Riferimento progettazione: `plans/architecture-ingestor.md`,
`plans/architecture-quiz-bank.md`.

## Test

- `tests/guidami_ai_patente_ingestor/repositories/test_article_repository.py` —
  `load`/`write` round-trip su fixture reali.
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_cleaner.py` —
  su fixture reali (`tests/.../fixtures/cds_sample.json`, `cap_sample.json`,
  copiate da dati reali CdS/CAP): rimozione markup inline da `text` e
  `paragraphs`, rimozione ordinali, markup inline a metà comma, marcatori
  standalone scartati senza perdere commi, titolo avvolto in parentesi
  spogliato, comma interamente avvolto con riferimento a nota scartato.
  `test_duplicated_ordinal_prefix_is_fully_stripped` (fixture art. 226 in
  `cds_sample.json`) verifica che l'ordinale duplicato (`"2. 2. Nell'archivio
  nazionale..."`) sia rimosso completamente.
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py` —
  casi limite: articolo interamente abrogato, `text=""`, comma singolarmente
  abrogato, numerazione non numerica con markup multiplo (su `Article` già
  puliti).
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_cleaning/test_cleaning_pipeline.py` —
  unit con `Mock(spec=ArticleRepository)`: pulizia di entrambe le source
  quando nessun output esiste, skip per source con `cleaned_path` già
  presente.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_cleaning/test_cleaning_pipeline_builder.py` —
  path `*_parsed_path` mancanti → `FileNotFoundError` aggregato.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline.py` —
  unit, nessun I/O reale: batching degli embedding, ordine
  `truncate()`→`bulk_insert()`, load di entrambe le fonti (`*_cleaned_path`)
  completato prima del chunking.
- `tests/guidami_ai_patente_ingestor/orchestrators/knowledge_indexing/test_indexing_pipeline_builder.py` —
  path `*_cleaned_path` mancanti → `FileNotFoundError` senza istanziare
  `LiteLLMEmbeddingClient`/`PostgresClient`.
- `tests/guidami_ai_patente_ingestor/configs/test_ingestor_config.py` —
  default path (`*_parsed_path`/`*_cleaned_path`/`quiz_bank_path`), default
  dei nomi tabella (`knowledge_chunks_table`/`quiz_questions_table`),
  `postgres: PostgresConnectionConfig` obbligatorio (`ValidationError` se
  assente con `_env_file=None`), immutabilità (`frozen=True`).
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_bank_repository.py` —
  `load` su fixture reale (`tests/.../fixtures/quiz_bank_sample.json`):
  mappatura in `QuizMainQuestion`/`QuizSubQuestion`.
- `tests/guidami_ai_patente_ingestor/services/quiz/test_quiz_question_mapper.py` —
  denormalizzazione `question_id`/`topic`, estrazione `image_filename` da
  path repo-relative (`PurePosixPath(...).name`), `image_filename=None` se
  assente, dedup su `(text.strip(), correct_answer, image)` (mantiene righe
  con stesso testo ma immagine o `correct_answer` diversi).
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_indexing/test_quiz_indexing_pipeline.py` —
  unit con `Mock(spec=...)` per repository/mapper/embedding_client: ordine
  load→map→assign_embeddings→truncate→bulk_insert; verifica batching degli
  embedding (stessa strategia di `test_indexing_pipeline.py`).
- `tests/guidami_ai_patente_ingestor/orchestrators/quiz_indexing/test_quiz_indexing_pipeline_builder.py` —
  `quiz_bank_path` mancante → `FileNotFoundError` senza istanziare
  `PostgresClient` o l'embedding client.
- `tests/guidami_ai_patente_ingestor/repositories/test_quiz_question_store_repository.py` —
  contro il Postgres del compose (no marker `integration`): `truncate` +
  `bulk_insert` su `quiz_questions` con colonna `embedding`, fixture `client`
  analoga a `test_postgres_client.py`.
- `tests/commons/clients/test_postgres_client.py` — aggiornato per
  `PostgresConnectionConfig` (host/port/user/password/dbname/sslmode) al
  posto di `VectorStoreConfig`/`database_url`; nessuna assert su
  `similarity_search` (rimosso).
- **Non ancora implementato**: test di integrazione end-to-end contro
  Postgres + modello reali con marker `@pytest.mark.integration` dedicato
  (i test Postgres attuali girano contro il compose locale ma non sono
  marcati).
