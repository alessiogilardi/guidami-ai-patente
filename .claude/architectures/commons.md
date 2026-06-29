# Package `src/commons/`

Riferimento progettazione: `plans/architecture-code-layout.md`,
`plans/implement/commons.md`, `plans/architecture-quiz-bank.md` (decisioni
7-8, refactor Postgres condiviso), `plans/ingest--agent-and-prompt-provider.md`,
`plans/ingest--data-preparation.md`,
`plans/ingest--orchestrator/01-embedding-service.md` (SP01 — EmbeddingService).

Componenti condivisi tra `guidami_ai_patente_ingestor` e l'app FastAPI (non
ancora avviata). `commons` non dipende da nessuno dei due.

## Layout

```
src/commons/
  agents/
    __init__.py              # re-esporta BaseAgent
    base_agent.py            # PromptRenderer, ConfigLoader, BaseAgent[T_out] — composizione su pydantic_ai.Agent
  configs/
    agent_config.py          # AgentConfig (frozen BaseModel) — modello YAML agente
  entities/
    knowledge/
      knowledge_chunk.py   # KnowledgeChunk — riga di knowledge_chunks (+ context: str = "")
    quiz/
      quiz_question.py     # QuizQuestion — riga di quiz_questions
  models/
    knowledge/
      retrieval_result.py     # RetrievalResult — chunk + score (similarity search)
  clients/
    embeddings/
      __init__.py                                  # re-esporta EmbeddingClient, LiteLLMEmbeddingClient,
                                                   # SentenceTransformerEmbeddingClient
      embedding_client.py                          # EmbeddingClient (interfaccia ABC)
      litellm_embedding_client.py                  # LiteLLMEmbeddingClient (cloud, OpenRouter)
      sentence_transformer_embedding_client.py     # SentenceTransformerEmbeddingClient (locale, bge-m3)
    __init__.py            # re-esporta tutti i client pubblici
    postgres_client.py     # PostgresClient — wrapper psycopg generico, table-agnostic
  configs/
    agent_config.py               # AgentConfig (frozen BaseModel) — re-esportato da commons/configs/__init__.py
    embedding_config.py           # EmbeddingConfig (frozen)
    postgres_connection_config.py # PostgresConnectionConfig (frozen)
  flowstep/                    # Pipeline framework leggero (Flow + Step) — non ancora integrato nel sistema
  services/
    __init__.py
    embeddings/
      __init__.py              # re-esporta Embeddable, Embedded, EmbeddingService
      embeddable.py            # Protocol Embeddable + Embedded (@runtime_checkable)
      embedding_service.py     # class EmbeddingService
```

## Decisioni implementate

- **`EmbeddingConfig`** (`BaseModel`, `frozen=True`): campi `model_name`
  (default `"openrouter/openai/text-embedding-3-small"`), `vector_dim: int =
  1536`, `dimensions: int | None = None` (Matryoshka opzionale — passato
  all'API se si usa `LiteLLMEmbeddingClient`), `timeout: float = 30.0`,
  `num_retries: int = 3`. Il valore di `vector_dim` deve corrispondere alla
  dimensione configurata nel DB (`VECTOR(1536)` in `db/init.sql`). Il campo
  `SentenceTransformerEmbeddingClient` rimane disponibile per sperimentazione
  offline ma non è il default di produzione.
- **`SentenceTransformerEmbeddingClient`**: implementazione locale via
  libreria **sentence-transformers**. Carica il modello con
  `SentenceTransformer(config.model_name)` al momento della costruzione
  (import a livello di modulo). Costruttore: `config: EmbeddingConfig`,
  `query_prefix: str = ""`, `passage_prefix: str = ""` — prefissi vuoti per
  default (stile bge-m3); passare prefissi espliciti per modelli asimmetrici
  come `intfloat/multilingual-e5-*`. `normalize_embeddings=True` sempre in
  entrambi i metodi. Sostituisce `E5SmallEmbeddingClient` (rimosso).
- **`LiteLLMEmbeddingClient`**: implementazione cloud via libreria
  **litellm**, instradato su **OpenRouter** (endpoint embeddings
  OpenAI-compatible). Riceve in costruzione un `EmbeddingConfig`; chiama
  `litellm.embedding(model=..., input=texts, ...)` passando `timeout`,
  `num_retries` e opzionalmente `dimensions`. La risposta viene ordinata per
  `data[i]["index"]` per garantire l'allineamento input↔output
  indipendentemente dall'ordine restituito dall'API. L'API key
  `OPENROUTER_API_KEY` è letta da litellm dall'ambiente (`.env`), senza
  lettura esplicita nel codice. Rimane disponibile come alternativa cloud per
  A/B di qualità.
- **`EmbeddingClient` (ABC)**: interfaccia `embed_query(text: str) ->
  list[float]` / `embed_passages(texts: list[str]) -> list[list[float]]`
  invariata — l'implementazione concreta è sostituibile senza cambiare i
  chiamanti (Dependency Inversion). Entrambe le implementazioni
  (`SentenceTransformerEmbeddingClient`, `LiteLLMEmbeddingClient`) sono
  esportate da `commons.clients`.
- **`PostgresConnectionConfig`** (`BaseModel`, `frozen=True`): sostituisce
  `VectorStoreConfig` (rimosso). Resta `BaseModel`, non `BaseSettings` —
  `commons` non legge env, i valori arrivano dal chiamante (il caricamento
  config resta a `main.py` dei rispettivi servizi, vedi
  `rules/python/architecture.md`). Campi: `host`, `port: int = 5432`, `user`,
  `password: SecretStr`, `dbname`, `sslmode: str | None = None`. **Nessun
  campo `table_name`**: il nome tabella è un dettaglio del repository che usa
  il client (decisione 7 del piano quiz-bank), non della connessione — un
  unico `PostgresConnectionConfig` è condiviso tra `knowledge_chunks` e
  `quiz_questions` (stesso Postgres, stesse credenziali).
- **`PostgresClient`**: wrapper `psycopg` v3 generico e **table-agnostic**
  con adapter `pgvector` registrato (`register_vector`), usabile come context
  manager (`__enter__`/`__exit__` chiude la connessione, più `close()`
  esplicito). Sostituisce `VectorStoreClient` (rimosso, incluso
  `similarity_search` — nessun consumer attuale). La connessione è costruita
  con `psycopg.conninfo.make_conninfo(host=..., port=..., user=...,
  password=config.password.get_secret_value(), dbname=...,
  sslmode=config.sslmode)` seguito da `psycopg.connect(conninfo,
  autocommit=True)` — `make_conninfo` filtra automaticamente `sslmode=None`.
  Metodi:
  - `truncate(table_name: str)` — `TRUNCATE TABLE {table}` con
    `sql.Identifier` (nome tabella passato dal chiamante, non dalla config);
  - `execute(query: sql.Composed, params: Sequence[object] | None = None)` —
    statement parametrico senza risultato (es. `DELETE ... WHERE source = %s`),
    un'unica esecuzione; necessario per operazioni di delete-by-key che non
    possono usare `TRUNCATE`;
  - `execute_many(query: sql.Composed, params_seq: Sequence[Sequence[object]])`
    — `cursor.executemany`, usato per i bulk insert dei repository;
  - `fetch(query: sql.Composed, params: Sequence[object] | None = None) ->
    list[tuple]` — `cursor.execute` + `fetchall`, pensato per le letture
    on-demand del futuro `QuizRepository`/`KnowledgeRepository` lato app.
  - I parametri vettoriali richiedono cast esplicito `%s::vector` nelle query
    (psycopg altrimenti adatta `list[float]` ad `array`, incompatibile con
    `<=>`).
- **`KnowledgeChunk`** (Pydantic, `commons/entities/knowledge/`): `source:
  Literal["cds", "cap"]`, `embedding: list[float] | None = None` (None prima
  dell'embedding), `context: str = ""` (contesto LLM del comma, colonna DB,
  default stringa vuota). Entità **DB-write-only**: nessuna property
  `embedded_text` — il testo da embeddare è sulla property omonima di
  `EmbeddableChunkModel` (DTO intermedio nell'ingestor). `KnowledgeChunk`
  soddisfa solo il protocollo `Embedded` (ha `embedding`), non `Embeddable`.
- **`QuizQuestion`** (Pydantic, `BaseModel`, `commons/entities/quiz/`): riga
  di `quiz_questions` — `number: str`, `question_id: int`, `topic: str`,
  `text: str`, `correct_answer: bool`, `image_filename: str | None = None`,
  `embedding: list[float] | None = None` (None prima dell'embedding, stesso
  pattern di `KnowledgeChunk`). Property `embedded_text -> str`: restituisce
  `f"{topic} {text}"` — testo prefissato dal topic della domanda, usato come
  input per l'embedding al posto del solo `text`.
- **`entities/` vs `models/`**: `KnowledgeChunk` e `QuizQuestion` sono entità
  di dominio (righe di tabella), in `commons/entities/`. `commons/models/`
  ospita DTO di layer/intermedi che non finiscono a DB. `commons/models/quiz/`
  è stato rimosso: i modelli intermedi del quiz bank (`QuizBankModel`/
  `QuizBankItemModel`, `EnrichedQuizModel`/`EnrichedQuizItemModel`,
  `EmbeddableQuizModel`, `ImageDescription`, rinominati in SP04-bis) e
  `EnrichedArticleModel` (insieme a `ParsedArticleModel` e `EmbeddableChunkModel`)
  vivono in `guidami_ai_patente_ingestor/models/knowledge/` perché
  sono DTO specifici dell'ingestor e non servono all'app FastAPI.
- **`Embeddable` Protocol** (`commons/services/embeddings/embeddable.py`,
  `@runtime_checkable`): espone una property `embedded_text: str` in sola lettura.
  Usato come tipo di input di `EmbeddingService.embed` — qualunque oggetto con
  quella property è accettato per structural subtyping senza ereditarietà.
- **`Embedded(Embeddable)` Protocol** (`@runtime_checkable`): estende `Embeddable`
  aggiungendo l'attributo scrivibile `embedding: list[float] | None`.
  `EmbeddableChunkModel` (ingestor) e `EmbeddableQuizModel` soddisfano entrambi i
  Protocol (verificato con `isinstance` nei test). `KnowledgeChunk` soddisfa
  solo `Embedded` (ha `embedding`) ma non `Embeddable` (non ha `embedded_text`):
  è DB-only, non partecipa all'embedding direttamente.
- **`EmbeddingService`** (`commons/services/embeddings/embedding_service.py`):
  - Costruttore `__init__(client: EmbeddingClient, batch_size: int)`: inietta il
    client e la dimensione del batch; alza `ValueError` se `batch_size < 1`.
  - Metodo `embed(items: Sequence[Embeddable]) -> list[list[float]]`: puro — non muta
    gli item in input, restituisce i vettori allineati 1:1 nello stesso ordine.
    Batching con ceiling division (`-(-len // batch_size)`); log per ogni batch
    nel formato `embedding batch {n}/{total} ({k} items)`. Delega a
    `EmbeddingClient.embed_passages([item.embedded_text for item in batch])`.
  - Import cross-package: `commons.clients.EmbeddingClient` via import assoluto;
    `embeddable.py` via import relativo (stesso package).
  - Il service **non** assegna `item.embedding`: la responsabilità di mutazione
    resta al caller (pipeline, SP02–SP04). Separazione puro/impuro esplicita.
- **`AgentConfig`** (Pydantic, `commons/configs/agent_config.py`, `frozen=True`):
  modella il contenuto di un file `configs/agents/<name>.yaml` — campi:
  `model_name`, `temperature: float = 0.0`, `max_tokens: int | None = None`,
  `timeout: float = 60.0`, `num_retries: int = 3`, `system: str`, `user: str`
  (template con placeholder `$var` in sintassi `string.Template`). Non esiste il
  campo `response_format`: l'output strutturato è gestito da PydanticAI tramite
  `output_type`. Re-esportato da `commons/configs/__init__.py`.
- **`PromptRenderer`** (`commons/agents/base_agent.py`): SRP — formatta il
  template utente via `string.Template.safe_substitute(**variables)` e allega
  immagini come `BinaryContent` (usa `mimetypes.guess_type`). Metodo:
  `render(variables, images=()) -> str | list[str | BinaryContent]`.
- **`ConfigLoader`** (`commons/agents/base_agent.py`): SRP/DIP — carica
  `AgentConfig` da YAML. Metodo statico: `from_yaml(agents_dir, name) ->
  AgentConfig`; lancia `FileNotFoundError` se il file non esiste.
- **`BaseAgent[T_out]`** (`commons/agents/base_agent.py`): usa Python 3.12
  native generics (`class BaseAgent[T_out]`). **Composizione** (non ereditarietà)
  su `pydantic_ai.Agent`, wrappato come `self._agent: Agent[None, T_out]`.
  - `__init__(config: AgentConfig, output_type: type[T_out])`: converte
    `model_name` sostituendo il primo `/` con `:` (es. `openrouter/google/model`
    → `openrouter:google/model`), costruisce `self._agent` con
    `defer_model_check=True` — l'API key (`OPENROUTER_API_KEY`) è verificata
    solo a runtime, non alla creazione.
  - Metodi: `run_prompt(variables, images)` (async), `run_prompt_sync(variables,
    images)` (sync). Entrambi delegano a `self._agent.run_sync` /
    `self._agent.run`; restituiscono il `RunResult` su cui il chiamante accede
    a `.output`.
  - Factory: `from_yaml(name, agents_dir, output_type) -> BaseAgent[T_out]` —
    usa `ConfigLoader.from_yaml` + `PromptRenderer`.
  - Property `core_agent`: espone `self._agent` per permettere
    `with agent.core_agent.override(model=TestModel(...))` nei test.
  Auth via `OPENROUTER_API_KEY` nell'ambiente — mai nello YAML né nel codice.

## Test

- `tests/commons/services/embeddings/test_embedding_service.py` — 8 test TDD
  senza marker `integration` (nessuna dipendenza esterna): allineamento
  lunghezza/ordine output; batching con `_RecordingFakeClient` (verifica numero
  di chiamate e testi per batch); input vuoto → lista vuota e zero chiamate;
  `ValueError` per `batch_size=0` e `batch_size=-1`; purezza (nessuna mutazione
  di `item.embedding`); conformità strutturale di `EmbeddableChunkModel` a
  `Embeddable` e `Embedded` via `isinstance`; conformità di
  `EmbeddableQuizModel` agli stessi Protocol.
- `tests/commons/clients/test_embedding_client.py` — test offline con mock di
  `litellm.embedding`: verifica costruzione risposta, ordinamento per `index`,
  separazione `embed_query`/`embed_passages`. Test `@pytest.mark.integration`
  (skippato senza `OPENROUTER_API_KEY`) verifica `len(vector) == 1536` contro
  l'API reale. Test per `SentenceTransformerEmbeddingClient`: `embed_query` e
  `embed_passages` con prefissi vuoti (bge-m3) e con prefissi espliciti
  (e5-style); verifica `len(vector) == config.vector_dim`.
- `tests/commons/clients/test_postgres_client.py` — contro il Postgres del
  compose (no marker `integration`): `truncate`, `execute_many`/`fetch` su
  `knowledge_chunks` (bulk insert + lettura ordinata).
- `tests/commons/entities/knowledge/test_knowledge_chunk.py` — default
  `embedding=None`, default `context=""`. Nessun test su `embedded_text`
  (`KnowledgeChunk` non ha questa property — è su `EmbeddableChunkModel`).
- `tests/commons/models/knowledge/test_retrieval_result.py` — wrapping di
  `KnowledgeChunk` in `RetrievalResult` con `score`.
- `tests/commons/agents/test_agent_config.py` — parsing da dict YAML;
  default applicati; campi obbligatori mancanti → `ValidationError`; `frozen=True`
  verifica immutabilità. (`AgentConfig` vive ora in `commons/configs/agent_config.py`
  ma i test rimangono in `tests/commons/agents/`.)
- `tests/commons/agents/test_base_agent.py` — YAML assente →
  `FileNotFoundError`; parametri YAML mappati su `model_settings` (`temperature`,
  `max_tokens`, `timeout`, `_max_output_retries`); `PromptRenderer.render`
  sostituisce i placeholder `$var`; con `images` la lista contiene `BinaryContent`;
  `core_agent` property usata con `agent.core_agent.override(model=TestModel(...))`
  nei test; `dict[int, str]` come `output_type` → PydanticAI wrappa sotto chiave
  `response`, il `FunctionModel` deve restituire `{"response": {...}}`.
