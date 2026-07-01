# Package `src/commons/`

Documents exclusively the `src/commons/` package.

Shared components between `guidami_ai_patente_ingestor` and the FastAPI app (not
yet started). `commons` does not depend on either.

## Layout

```
src/commons/
  use_cases/
    __init__.py              # re-esporta UseCase, AsyncUseCase, ForEach
    use_case.py              # UseCase[T_In, T_Out](ABC) + AsyncUseCase[T_In, T_Out](ABC)
    for_each.py              # ForEach[T, U](UseCase[list[T], list[U]]) — applica Callable[[T], U] a ogni elemento
  agents/
    __init__.py              # re-esporta BaseAgent
    base_agent.py            # PromptRenderer, ConfigLoader, BaseAgent[T_In: BaseModel, T_Out] — composizione su pydantic_ai.Agent
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
  services/
    __init__.py
    embeddings/
      __init__.py              # re-esporta Embeddable, Embedded, EmbeddingService
      embeddable.py            # Protocol Embeddable + Embedded (@runtime_checkable)
      embedding_service.py     # class EmbeddingService
```

## Implemented decisions

- **`UseCase[T_In, T_Out]`** (`commons/use_cases/use_case.py`): generic ABC with
  two type parameters that standardises the contract of stateless components with a
  single operation. Abstract method `execute(request: T_In) -> T_Out`; `__call__`
  is marked `@final` and delegates to `execute` — every `UseCase` is directly
  callable (compatible with `ApplyStep`/`ForEach` that receive a callable). Adopted
  by `EmbeddingService`, `ArticleCleaner`, `ArticleChunker`, `FlattenQuiz`,
  `ToEmbeddableQuiz`, `ContextEnricher`, `ImageDescriptionEnricher`. The public
  method of all is named `execute`. Maintains the pure/impure separation: the
  contract does not prescribe side effects.
- **`AsyncUseCase[T_In, T_Out]`** (`commons/use_cases/use_case.py`): async
  variant — same structure as `UseCase` but `execute` is `async`. `__call__`
  is `@final async`. Added without active consumers: establishes the contract for
  future async implementations (e.g. embedding or LLM calls with `asyncio`).
- **`ForEach[T, U]`** (`commons/use_cases/for_each.py`): `UseCase[list[T],
  list[U]]` that wraps a `Callable[[T], U]` and applies it to each element of the
  input list. Accepts both `UseCase` instances (invoked via `__call__`) and static
  methods (e.g. `QuizMapper.from_embeddable_to_quiz_question`). Used in flow
  builders to wrap 1:1 mappers in a list→list callable compatible with `ApplyStep`.
  Trade-off: `fn: Callable[[T], U]` is broader than `UseCase[T, U]` — allows
  passing static methods without an extra wrapper.
- **`EmbeddingConfig`** (`BaseModel`, `frozen=True`): fields `model_name`
  (default `"openrouter/openai/text-embedding-3-small"`), `vector_dim: int =
  1536`, `dimensions: int | None = None` (optional Matryoshka — passed to the API
  when using `LiteLLMEmbeddingClient`), `timeout: float = 30.0`,
  `num_retries: int = 3`. The value of `vector_dim` must match the dimension
  configured in the DB (`VECTOR(1536)` in `db/init.sql`). The
  `SentenceTransformerEmbeddingClient` option remains available for offline
  experimentation but is not the production default.
- **`SentenceTransformerEmbeddingClient`**: local implementation via the
  **sentence-transformers** library. Loads the model with
  `SentenceTransformer(config.model_name)` at construction time (module-level
  import). Constructor: `config: EmbeddingConfig`, `query_prefix: str = ""`,
  `passage_prefix: str = ""` — empty prefixes by default (bge-m3 style); pass
  explicit prefixes for asymmetric models such as `intfloat/multilingual-e5-*`.
  `normalize_embeddings=True` always in both methods. Replaces
  `E5SmallEmbeddingClient` (removed).
- **`LiteLLMEmbeddingClient`**: cloud implementation via the **litellm** library,
  routed through **OpenRouter** (OpenAI-compatible embeddings endpoint). Receives
  an `EmbeddingConfig` at construction; calls
  `litellm.embedding(model=..., input=texts, ...)` passing `timeout`,
  `num_retries` and optionally `dimensions`. The response is sorted by
  `data[i]["index"]` to guarantee input↔output alignment regardless of the order
  returned by the API. The `OPENROUTER_API_KEY` is read by litellm from the
  environment (`.env`), with no explicit read in the code. Remains available as a
  cloud alternative for quality A/B testing.
- **`EmbeddingClient` (ABC)**: interface `embed_query(text: str) ->
  list[float]` / `embed_passages(texts: list[str]) -> list[list[float]]`
  unchanged — the concrete implementation is swappable without changing callers
  (Dependency Inversion). Both implementations
  (`SentenceTransformerEmbeddingClient`, `LiteLLMEmbeddingClient`) are exported
  from `commons.clients`.
- **`PostgresConnectionConfig`** (`BaseModel`, `frozen=True`): replaces
  `VectorStoreConfig` (removed). Stays as `BaseModel`, not `BaseSettings` —
  `commons` does not read env vars; values arrive from the caller (config loading
  stays in `main.py` of the respective services, see
  `rules/python/architecture.md`). Fields: `host`, `port: int = 5432`, `user`,
  `password: SecretStr`, `dbname`, `sslmode: str | None = None`. **No
  `table_name` field**: the table name is a detail of the repository using the
  client (decision 7 of the quiz-bank plan), not of the connection — a single
  `PostgresConnectionConfig` is shared between `knowledge_chunks` and
  `quiz_questions` (same Postgres, same credentials).
- **`PostgresClient`**: generic, **table-agnostic** `psycopg` v3 wrapper with the
  `pgvector` adapter registered (`register_vector`), usable as a context manager
  (`__enter__`/`__exit__` closes the connection, plus explicit `close()`).
  Replaces `VectorStoreClient` (removed, including `similarity_search` — no
  current consumers). The connection is built with
  `psycopg.conninfo.make_conninfo(host=..., port=..., user=...,
  password=config.password.get_secret_value(), dbname=...,
  sslmode=config.sslmode)` followed by `psycopg.connect(conninfo,
  autocommit=True)` — `make_conninfo` automatically filters `sslmode=None`.
  Methods:
  - `truncate(table_name: str)` — `TRUNCATE TABLE {table}` with
    `sql.Identifier` (table name passed by the caller, not from config);
  - `execute(query: sql.Composed, params: Sequence[object] | None = None)` —
    parameterised statement without result (e.g. `DELETE ... WHERE source = %s`),
    single execution; required for delete-by-key operations that cannot use
    `TRUNCATE`;
  - `execute_many(query: sql.Composed, params_seq: Sequence[Sequence[object]])`
    — `cursor.executemany`, used for repository bulk inserts;
  - `fetch(query: sql.Composed, params: Sequence[object] | None = None) ->
    list[tuple]` — `cursor.execute` + `fetchall`, designed for on-demand reads
    in the future `QuizRepository`/`KnowledgeRepository` on the app side.
  - Vector parameters require explicit `%s::vector` cast in queries (otherwise
    psycopg adapts `list[float]` to `array`, which is incompatible with `<=>`).
- **`KnowledgeChunk`** (Pydantic, `commons/entities/knowledge/`): `source:
  Literal["cds", "cap"]`, `embedding: list[float] | None = None` (None before
  embedding), `context: str = ""` (LLM context for the article paragraph, DB
  column, default empty string). **DB-write-only** entity: no `embedded_text`
  property — the text to embed is on the same-named property of
  `EmbeddableChunkModel` (intermediate DTO in the ingestor). `KnowledgeChunk`
  satisfies only the `Embedded` protocol (has `embedding`), not `Embeddable`.
- **`QuizQuestion`** (Pydantic, `BaseModel`, `commons/entities/quiz/`): row of
  `quiz_questions` — `number: str`, `question_id: int`, `topic: str`,
  `text: str`, `correct_answer: bool`, `image_filename: str | None = None`,
  `embedding: list[float] | None = None` (None before embedding, same pattern as
  `KnowledgeChunk`). Property `embedded_text -> str`: returns `f"{topic} {text}"`
  — text prefixed with the question topic, used as embedding input instead of
  `text` alone.
- **`entities/` vs `models/`**: `KnowledgeChunk` and `QuizQuestion` are domain
  entities (table rows), in `commons/entities/`. `commons/models/` hosts
  layer/intermediate DTOs that do not go to the DB. `commons/models/quiz/` has
  been removed: the quiz bank intermediate models (`QuizBankModel`/
  `QuizBankItemModel`, `EnrichedQuizModel`/`EnrichedQuizItemModel`,
  `EmbeddableQuizModel`, `ImageDescription`, renamed in SP04-bis) and
  `EnrichedArticleModel` (together with `ParsedArticleModel` and
  `EmbeddableChunkModel`) live in `guidami_ai_patente_ingestor/models/knowledge/`
  because they are ingestor-specific DTOs not needed by the FastAPI app.
- **`Embeddable` Protocol** (`commons/services/embeddings/embeddable.py`,
  `@runtime_checkable`): exposes a read-only `embedded_text: str` property.
  Used as the input type of `EmbeddingService.embed` — any object with that
  property is accepted via structural subtyping without inheritance.
- **`Embedded(Embeddable)` Protocol** (`@runtime_checkable`): extends `Embeddable`
  by adding the writable `embedding: list[float] | None` attribute.
  `EmbeddableChunkModel` (ingestor) and `EmbeddableQuizModel` satisfy both
  Protocols (verified with `isinstance` in the tests). `KnowledgeChunk` satisfies
  only `Embedded` (has `embedding`) but not `Embeddable` (no `embedded_text`):
  it is DB-only and does not participate in embedding directly.
- **`EmbeddingService`** (`commons/services/embeddings/embedding_service.py`,
  implements `UseCase[Sequence[Embeddable], list[list[float]]]`):
  - Constructor `__init__(client: EmbeddingClient, batch_size: int)`: injects
    the client and batch size; raises `ValueError` if `batch_size < 1`.
  - Method `execute(items: Sequence[Embeddable]) -> list[list[float]]`: pure —
    does not mutate input items, returns vectors aligned 1:1 in the same order.
    Batching with ceiling division (`-(-len // batch_size)`); logs each batch in
    the format `embedding batch {n}/{total} ({k} items)`. Delegates to
    `EmbeddingClient.embed_passages([item.embedded_text for item in batch])`.
  - Cross-package import: `commons.clients.EmbeddingClient` via absolute import;
    `embeddable.py` via relative import (same package).
  - The service does **not** assign `item.embedding`: mutation responsibility
    stays with the caller (pipeline). Explicit pure/impure separation.
- **`AgentConfig`** (Pydantic, `commons/configs/agent_config.py`, `frozen=True`):
  models the content of a `configs/agents/<name>.yaml` file — fields:
  `model_name`, `temperature: float = 0.0`, `max_tokens: int | None = None`,
  `timeout: float = 60.0`, `num_retries: int = 3`, `system: str`, `user: str`
  (template with `$var` placeholders in `string.Template` syntax). No
  `response_format` field: structured output is handled by PydanticAI via
  `output_type`. Re-exported from `commons/configs/__init__.py`.
- **`PromptRenderer`** (`commons/agents/base_agent.py`): SRP — formats the user
  template via `string.Template.safe_substitute(**variables)` and attaches images
  as `BinaryContent` (uses `mimetypes.guess_type`). Method:
  `render(variables: dict, images=()) -> str | list[str | BinaryContent]`.
  The caller (`BaseAgent`) extracts template variables from the `T_In` request via
  `request.model_dump()` before invoking `render`.
- **`ConfigLoader`** (`commons/agents/base_agent.py`): SRP/DIP — loads
  `AgentConfig` from YAML. Static method: `from_yaml(agents_dir, name) ->
  AgentConfig`; raises `FileNotFoundError` if the file does not exist.
- **`BaseAgent[T_In: BaseModel, T_Out]`** (`commons/agents/base_agent.py`): uses Python 3.12
  native generics. **Composition** (not inheritance) over `pydantic_ai.Agent`,
  wrapped as `self._agent: Agent[None, T_Out]`. `T_In` is constrained to
  `BaseModel`: every agent receives and returns typed Pydantic DTOs, not raw
  dictionaries.
  - `__init__(config: AgentConfig, output_type: type[T_Out])`: converts
    `model_name` by replacing the first `/` with `:` (e.g. `openrouter/google/model`
    → `openrouter:google/model`), builds `self._agent` with
    `defer_model_check=True` — the API key (`OPENROUTER_API_KEY`) is verified
    only at runtime, not at construction.
  - Methods: `run_prompt(request: T_In, images)` (async), `run_prompt_sync(request: T_In,
    images)` (sync). They extract template variables via `request.model_dump()`
    and pass them to `PromptRenderer.render`. Both delegate to `self._agent.run_sync` /
    `self._agent.run`; return `.output` typed as `T_Out`.
  - Factory: `from_yaml(name, agents_dir, output_type) -> BaseAgent[T_In, T_Out]` —
    uses `ConfigLoader.from_yaml` + `PromptRenderer`.
  - Property `core_agent`: exposes `self._agent` to allow
    `with agent.core_agent.override(model=TestModel(...))` in tests.
  Auth via `OPENROUTER_API_KEY` in the environment — never in the YAML or in the code.

## Tests

- `tests/commons/use_cases/test_for_each.py` — `ForEach(fn)` applied to an empty
  list, a single-element list, a multi-element list; verifies the callable is
  invoked once per element in the correct order; compatibility with static methods
  and with `UseCase` instances.
- `tests/commons/services/embeddings/test_embedding_service.py` — 8 TDD tests
  without `integration` marker (no external dependencies): output length/order
  alignment; batching with `_RecordingFakeClient` (verifies number of calls and
  texts per batch); empty input → empty list and zero calls; `ValueError` for
  `batch_size=0` and `batch_size=-1`; purity (no mutation of `item.embedding`);
  structural conformance of `EmbeddableChunkModel` to `Embeddable` and `Embedded`
  via `isinstance`; conformance of `EmbeddableQuizModel` to the same Protocols.
  The tested method is `execute` (no longer `embed` — renamed with the migration
  to `UseCase`).
- `tests/commons/clients/test_embedding_client.py` — offline tests with
  `litellm.embedding` mock: verifies response construction, sorting by `index`,
  separation of `embed_query`/`embed_passages`. `@pytest.mark.integration` test
  (skipped without `OPENROUTER_API_KEY`) verifies `len(vector) == 1536` against
  the real API. Tests for `SentenceTransformerEmbeddingClient`: `embed_query` and
  `embed_passages` with empty prefixes (bge-m3) and with explicit prefixes
  (e5-style); verifies `len(vector) == config.vector_dim`.
- `tests/commons/clients/test_postgres_client.py` — against the compose Postgres
  (no `integration` marker): `truncate`, `execute_many`/`fetch` on
  `knowledge_chunks` (bulk insert + ordered read).
- `tests/commons/entities/knowledge/test_knowledge_chunk.py` — default
  `embedding=None`, default `context=""`. No tests for `embedded_text`
  (`KnowledgeChunk` does not have this property — it is on `EmbeddableChunkModel`).
- `tests/commons/models/knowledge/test_retrieval_result.py` — wrapping
  `KnowledgeChunk` in `RetrievalResult` with `score`.
- `tests/commons/agents/test_agent_config.py` — parsing from YAML dict; defaults
  applied; missing required fields → `ValidationError`; `frozen=True` verifies
  immutability. (`AgentConfig` now lives in `commons/configs/agent_config.py`
  but the tests remain in `tests/commons/agents/`.)
- `tests/commons/agents/test_base_agent.py` — missing YAML → `FileNotFoundError`;
  YAML parameters mapped to `model_settings` (`temperature`, `max_tokens`,
  `timeout`, `_max_output_retries`); `PromptRenderer.render` substitutes `$var`
  placeholders; with `images` the list contains `BinaryContent`; `core_agent`
  property used with `agent.core_agent.override(model=TestModel(...))` in tests;
  `dict[int, str]` as `output_type` → PydanticAI wraps under the `response` key,
  the `FunctionModel` must return `{"response": {...}}`.
