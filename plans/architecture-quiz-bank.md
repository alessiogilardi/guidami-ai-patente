# Ingestion del quiz bank — tabella relazionale

Riferimento: [architecture-index.md](architecture-index.md),
[architecture-ingestor.md](architecture-ingestor.md) (pattern di pipeline
condiviso), [tech-stack.md](tech-stack.md),
[architecture-code-layout.md](architecture-code-layout.md).

## Dati sorgente

`data/parsed/quiz-patente-ab/quiz-patente-ab.json` — 715 domande madri, ognuna
con `question_id`, `topic`, `sub_questions` (lista di `number`, `text`,
`correct_answer`, `image` opzionale). Totale 7106 sotto-domande.

Verifiche empiriche sul file:

- `number` è unico sui 7106 record ma è una **stringa** (`"21810"`), non un
  intero.
- Ogni domanda madre ha **al più un'immagine distinta** (0 madri con >1
  immagine): l'immagine è di fatto un attributo della domanda madre,
  condiviso dalle sotto-domande che la referenziano.
- 2958/7106 sotto-domande non hanno il campo `image` (domande puramente
  testuali).
- 8 sotto-domande sono **duplicati esatti** (stesso testo, risposta e
  immagine) → vanno deduplicate in fase di map (vedi decisione 2).
- Il campo `image`, quando presente, contiene un path repo-relative completo
  (`data/processed/quiz-patente-ab/images/<uuid>.jpeg`) che punta a una
  directory (`data/processed/`) diversa da quella effettiva (`data/parsed/`)
  — path già stantio nella fonte. Risolto non salvando path completi in DB,
  vedi decisione 4.

## Schema tabella

```sql
CREATE TABLE quiz_questions (
    id              BIGSERIAL PRIMARY KEY,            -- surrogate, coerente con knowledge_chunks
    number          TEXT NOT NULL,                    -- id sotto-domanda dall'import: informativo
    question_id     INTEGER NOT NULL,                 -- id domanda madre, denormalizzato (da confermare il tipo nel JSON, vedi "Punti aperti")
    topic           TEXT NOT NULL,
    text            TEXT NOT NULL,
    correct_answer  BOOLEAN NOT NULL,
    image_filename  TEXT                              -- nome file immagine, NULL se assente; base dir risolta da config (decisione 4)
);

CREATE INDEX idx_quiz_questions_topic ON quiz_questions (topic);
CREATE INDEX idx_quiz_questions_question_id ON quiz_questions (question_id);
```

`CREATE TABLE` in `db/init.sql`, coerente con `knowledge_chunks` (vedi
[architecture-ingestor.md](architecture-ingestor.md), decisione 7).

> 📌 **Incremento successivo** — embedding offline dei quiz: a `quiz_questions`
> viene aggiunta la colonna `embedding VECTOR(1024)`, popolata da `ingest-quiz` con
> `bge-m3`, così il giudice LLM non embedda a runtime. Schema e step di pipeline
> descritti in [ingest--embedding-bge-m3.md](ingest--embedding-bge-m3.md) (sezione
> "Embedding dei quiz offline"), consumato da
> [ingest--llm-as-judge.md](ingest--llm-as-judge.md).

## Decisioni

1. **Granularità: una riga per sotto-domanda (flat)**. Il `QuizRepository`
   dell'app e l'`AnswerChecker` operano su sotto-domande singole — uno schema
   flat evita join per servire una domanda e per il check deterministico
   `correct_answer`. `question_id` e `topic` sono denormalizzati su ogni riga
   (provengono dalla domanda madre nel JSON sorgente).

2. **Identità di riga = surrogate `BIGSERIAL`; dedup dei duplicati esatti**.
   In v1 nulla referenzia `quiz_questions` (lo storico utente è v2, vedi
   "Possibili estensioni future"), quindi non serve una chiave di contenuto
   stabile tra import: una PK surrogate è sufficiente e coerente con
   `knowledge_chunks`. `number` resta come colonna informativa dell'ultimo
   import, **non** come identità (è una business key della fonte la cui
   stabilità non è garantita tra import PDF — aggiornamento atteso a ~1 anno).

   L'unico problema di qualità dati indipendente dalla scelta della PK sono gli
   **8 duplicati esatti** (stesso testo, risposta e immagine): vanno deduplicati
   in fase di map (tenere una riga, loggare un warning), altrimenti l'utente
   vedrebbe la stessa domanda più volte. La deduplica si fa confrontando la
   tripla `(testo_normalizzato, correct_answer, identità_immagine)` — non il
   solo testo né `number` (vedi analisi empirica in "Possibili estensioni
   future").

3. **Full reload (truncate + insert), come `knowledge_chunks`**. La
   re-ingestion è `TRUNCATE quiz_questions` + bulk insert delle righe mappate,
   ri-eseguibile a ogni re-parse. Stessa motivazione di
   [architecture-ingestor.md](architecture-ingestor.md): a questa scala
   (~7100 righe, secondi) la semplicità di "drop & rebuild" supera l'upsert
   incrementale ed evita bug di sincronizzazione quando una domanda sparisce
   dalla fonte. Nessun soft-delete, nessuna transazione di upsert: non c'è
   storico utente da preservare in v1. La meccanica di identità stabile +
   soft-delete (o snapshot nel tentativo) si introduce **insieme** a
   `user_quiz_attempts`, quando la forma della FK è nota — vedi "Possibili
   estensioni future".

4. **`image_filename` = solo filename, base dir da config**. La riga salva
   **solo il nome del file** (così come prodotto dal parser), `NULL` se
   assente; la base dir delle immagini è risolta via config. Questo evita di
   accoppiare il contenuto del DB al layout fisico del repo e chiude
   l'incoerenza `data/processed` vs `data/parsed` osservata nei dati sorgente,
   **senza dipendere** da un refactor del parser. La stabilità dei nomi file
   tra re-parse (content-addressing `{md5}.{ext}`) è un miglioramento
   desiderabile ma indipendente e non bloccante per questa pipeline — vedi
   "Task collegati".

5. **Granularità servita all'utente**. L'app, in v1, serve **una
   sotto-domanda random alla volta**, evitando di riproporre quelle già viste
   nella sessione corrente, per un numero di domande pari a quelle
   dell'esame. Evoluzione futura: le N domande di un "esame" variano per
   topic e provengono da madri diverse (la composizione esatta sarà oggetto
   di valutazione dedicata, non di questo piano). Lo schema flat regge
   entrambi gli scenari: la selezione opera sulla PK e gli indici su
   `topic`/`question_id` supportano la varietà futura — nessuna
   tabella-gruppo necessaria ora.

6. **`QuizRepository` Postgres-backed, letture on-demand, separato dal
   repository di scrittura**. Sostituisce il caricamento JSON in-memory
   previsto in v1 (vedi sezione "Tre tipi di memoria" in
   [architecture-index.md](architecture-index.md)). Query on-demand al DB (no
   cache in-memory delle ~7100 righe) — stesso pattern di dipendenza-da-Postgres
   già adottato per `KnowledgeRepository`.

   Le operazioni di lettura (app: random/filtro topic/esclusione viste) e di
   scrittura (ingestor: truncate + insert) sono asimmetriche → repository
   distinti per servizio (Interface Segregation), entrambi sullo stesso
   `PostgresClient` generico (decisione 7):
   - ingestor: repository di scrittura su `quiz_questions` (truncate + bulk insert);
   - app: `QuizRepository` di lettura.

   L'API esatta di `QuizRepository` (selezione random, filtro per topic,
   esclusione domande già viste in sessione) è un dettaglio di
   implementazione da definire in quella fase; lo schema sopra la supporta
   tramite gli indici su `topic` e `question_id`.

7. **Config Postgres condivisa: `PostgresConnectionConfig` unico, nomi
   tabella nei repository**. `knowledge_chunks` e `quiz_questions` vivono
   nello stesso Postgres con le stesse credenziali. I campi di connessione
   (`host`, `port`, `user`, `password`, `dbname`, `sslmode`) sono estratti in
   un `PostgresConnectionConfig` **unico, top-level** sul config radice di
   ciascun servizio — niente doppia env-var: `POSTGRES__USER`/
   `POSTGRES__PASSWORD` (rinominate da `VECTOR_STORE__USER`/`PASSWORD`, vedi
   `.env.example`).

   I **nomi tabella** (`knowledge_chunks`, `quiz_questions`) sono valori di
   configurazione (`IngestorConfig`/futuro `AppConfig`), iniettati nei
   **repository** — non nei client. `VectorStoreConfig`/`QuizStoreConfig`
   (connessione + tabella, come ipotizzato inizialmente) sono **eliminati** a
   favore di questo schema più semplice. Comporta un refactor di
   `VectorStoreConfig`/`IngestorConfig`/`.env.example` e dei relativi test
   esistenti. Vedi [architecture-code-layout.md](architecture-code-layout.md).

8. **Client generico + repository table-aware**. Il nome tabella appartiene
   al repository, non al client:
   - `commons/clients/`: **`PostgresClient`** generico e table-agnostic su
     `PostgresConnectionConfig` (connect/execute/fetch/copy, registrazione
     adapter pgvector). `VectorStoreClient`/ipotetico `QuizStoreClient`
     legati a una singola tabella **spariscono**.
   - Pipeline separata: nuovo orchestrator
     `orchestrators/quiz_indexing/quiz_indexing_pipeline.py` nell'ingestor,
     nessuno step di "cleaning"/"embedding" (il JSON del quiz bank non ha
     markup da pulire) — load diretto da `data/parsed/`. Comando CLI dedicato
     `uv run ingest-quiz`, seguendo la convenzione di `ingest-knowledge`. Un
     comando separato perché le due pipeline hanno step diversi (chunk+embed vs
     map+dedup) e possono essere eseguite indipendentemente, pur condividendo
     la stessa strategia di store (truncate + insert).

## Flusso di ingestion

```
orchestrators/quiz_indexing/quiz_indexing_pipeline.py

1. Load: legge data/parsed/quiz-patente-ab/quiz-patente-ab.json
2. Map:  per ogni domanda madre, per ogni sub_question -> riga quiz_questions
         (denormalizza question_id/topic, image_filename = nome file o NULL se
         "image" assente; dedup dei duplicati esatti, vedi decisione 2)
3. Store: TRUNCATE quiz_questions + bulk insert delle righe mappate
```

## Task collegati

- **Content-addressing immagini parser** (decisione 4, *non bloccante*):
  `src/parsers/questions_pdf.py` calcola già `md5(img_bytes)` ma nomina il
  file con `uuid.uuid4()` casuale (instabile tra re-parse). Nominarli
  `{md5}.{ext}` darebbe filename stabili e dedup globale delle immagini. È un
  miglioramento desiderabile ma **indipendente** dalla pipeline `quiz_indexing`
  (che salva il filename così com'è) e tocca `parsers/`, fuori dal perimetro di
  `guidami_ai_patente_ingestor`/`commons` → task separato, pianificabile
  quando comodo.

## Possibili estensioni future

- **Progress tracking utente (v2)**: una tabella separata (es.
  `user_quiz_attempts`) per tracciare le risposte date per sessione/utente —
  coerente con la nota su persistenza sessione in
  [architecture-index.md](architecture-index.md) (sezione 2). È il momento in
  cui serve un'**identità di riga stabile tra import** (oggi non necessaria,
  vedi decisione 2): solo allora si conosce la forma reale della relazione e si
  sceglie tra due pattern, da valutare in quella fase:
  - *snapshot nel tentativo*: la riga `user_quiz_attempts` copia testo/risposta
    al momento della risposta → il tentativo possiede la propria verità
    storica, `quiz_questions` resta un dettaglio rigenerabile a full reload
    (nessuna modifica a questo schema);
  - *identità di contenuto + soft-delete*: `question_uid = hash(testo_norm +
    correct_answer + identità_immagine)` come chiave referenziata, con
    `is_deleted`/`deleted_at` al posto del truncate, così lo storico non viene
    distrutto e le domande rimosse restano referenziabili.

  Analisi empirica a supporto della scelta della chiave di contenuto (righe
  perse se la chiave fosse identità):

  | Chiave | Domande distinte | Righe perse |
  |---|---|---|
  | solo testo | 6818 | 288 |
  | testo + risposta | 6874 | 232 |
  | testo + risposta + `has_image` (bool) | 6875 | 231 |
  | testo + risposta + **identità immagine** | 7098 | **8** |

  Le affermazioni sono riusate su segnali diversi (es. "Il segnale raffigurato
  indica una strada chiusa" sotto due immagini diverse): un booleano
  `has_image` è quasi inutile. Serve l'**identità del contenuto dell'immagine**
  (che dipende dal content-addressing del parser, vedi "Task collegati"). Le 8
  collisioni residue sono i duplicati esatti già deduplicati in v1 (decisione
  2). Questa analisi è la ragione per cui, *quando* si introdurrà la chiave di
  contenuto, includerà l'identità immagine — ma non c'è motivo di anticiparla
  ora.

## Punti aperti

- ~~Verificare il tipo di `question_id` nel JSON sorgente (assunto `INTEGER`
  nello schema sopra).~~ Risolto: nel JSON è una stringa numerica (es.
  `"4328"`), ma `QuizMainQuestion.question_id: int` la converte (coercizione
  lax di Pydantic v2) e la colonna `INTEGER` è confermata corretta.

## Stato

**Implementato (v1, decisioni 1-8 tutte chiuse).**

- `commons/configs/postgres_connection_config.py`,
  `commons/clients/postgres_client.py`: config e client Postgres generici,
  `VectorStoreConfig`/`VectorStoreClient` rimossi (decisioni 7-8).
- `commons/entities/quiz/quiz_question.py`: `QuizQuestion` (entità di
  dominio, non DTO — spostata da `commons/models/` in revisione successiva,
  vedi nota su `architecture-code-layout.md`).
- `guidami_ai_patente_ingestor/entities/quiz_bank.py`: `QuizMainQuestion`,
  `QuizSubQuestion`.
- `guidami_ai_patente_ingestor/repositories/quiz_bank_repository.py`:
  `QuizBankRepository.load`.
- `guidami_ai_patente_ingestor/services/quiz/quiz_question_mapper.py`:
  `QuizQuestionMapper` — flatten, denormalizza `question_id`/`topic`,
  `image_filename` da `PurePosixPath(image).name`, dedup su
  `(text.strip(), correct_answer, image)` con `logger.warning`.
- `guidami_ai_patente_ingestor/repositories/quiz_question_store_repository.py`:
  `QuizQuestionStoreRepository` (truncate + bulk insert).
- `guidami_ai_patente_ingestor/orchestrators/quiz_indexing/`:
  `QuizIndexingPipeline` + `QuizIndexingPipelineBuilder`.
- `guidami_ai_patente_ingestor/quiz_main.py` + `reset_quiz_db.py`, comandi CLI
  `uv run ingest-quiz` / `uv run reset-quiz-db`.
- `db/init.sql`: tabella `quiz_questions` + indici su `topic`/`question_id`.
- `.env.example`/`.env`: `VECTOR_STORE__*` → `POSTGRES__*`.
- Test unit + integration (repository, mapper, pipeline, builder, config).

Eseguito end-to-end contro Postgres locale: 715 domande madri caricate, 8
duplicati esatti scartati (loggati a `WARNING`), 7098 righe inserite in
`quiz_questions`. `uv run pytest` (55 passed), `ruff check` e `pyright` puliti
sul codice toccato (errori residui in `src/parsers`, `src/scrapers`,
`src/guidami_ai_patente` sono preesistenti e fuori scope).

**Non implementato / rinviato**:

- `QuizRepository` di lettura (decisione 6) — appartiene all'applicativo
  backend (FastAPI), non a questo ingestor; pianificato in
  [architecture-code-layout.md](architecture-code-layout.md) quando si avvia
  quel servizio.
- Content-addressing immagini nel parser (vedi "Task collegati") — task
  indipendente, non bloccante.
- Estensioni v2 (`user_quiz_attempts`, identità di contenuto + soft-delete) —
  rinviate come da decisione 3, nessuna modifica allo schema attuale
  necessaria nel frattempo.
