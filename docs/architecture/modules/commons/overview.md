# Shared packages: `src/commons/` and `src/domain/`

Documents the `src/commons/` and `src/domain/` packages.

`commons` provides shared infrastructure (clients, configs, utils, agents, use-cases,
services) between `guidami_ai_patente_ingestor` and the FastAPI app (not yet started).
`domain` holds the innermost ring of the Clean Architecture: entities (DB-row models)
and domain-level DTOs shared across packages. Neither `commons` nor `domain` depends
on the ingestor or the app.

## Layout

```
src/commons/
├── use_cases/
│   ├── __init__.py              # re-exports UseCase, AsyncUseCase, ForEach
│   ├── use_case.py              # UseCase[T_In, T_Out](ABC) + AsyncUseCase[T_In, T_Out](ABC)
│   └── for_each.py              # ForEach[T, U](UseCase[list[T], list[U]]) — applies Callable[[T], U] to each element
├── agents/
│   ├── __init__.py              # re-exports BaseAgent
│   └── base_agent.py            # PromptRenderer, BaseAgent[T_In: BaseModel, T_Out] — composition over pydantic_ai.Agent
├── repositories/
│   ├── __init__.py              # re-exports FileRepository, JsonRepository, YamlRepository
│   └── file_repository/
│       ├── __init__.py                      # explicit re-exports (AS aliases)
│       ├── file_repository_protocol.py      # FileRepository[T] (Protocol) — load / write
│       ├── _base_file_repository.py         # BaseFileRepository[T](ABC) — (de)serialisation + type inference
│       ├── json_repository.py               # JsonRepository[T](BaseFileRepository[T])
│       └── yaml_repository.py               # YamlRepository[T](BaseFileRepository[T])
├── clients/
│   ├── embeddings/
│   │   ├── __init__.py                                  # re-exports EmbeddingClient, LiteLLMEmbeddingClient,
│   │   │                                                # SentenceTransformerEmbeddingClient
│   │   ├── embedding_client.py                          # EmbeddingClient (ABC interface)
│   │   ├── litellm_embedding_client.py                  # LiteLLMEmbeddingClient (cloud, OpenRouter)
│   │   └── sentence_transformer_embedding_client.py     # SentenceTransformerEmbeddingClient (local, bge-m3)
│   ├── file_system/
│   │   ├── __init__.py                              # re-exports BaseFileSystemClient, 4 interfaces, 2 concrete clients
│   │   ├── _base_file_system_client.py              # BaseFileSystemClient — path security mixin
│   │   ├── interfaces/
│   │   │   ├── __init__.py
│   │   │   ├── file_reader.py                       # FileReaderInterface (ABC, sync)
│   │   │   ├── file_writer.py                       # FileWriterInterface (ABC, sync)
│   │   │   ├── async_file_reader.py                 # AsyncFileReaderInterface (ABC, async)
│   │   │   └── async_file_writer.py                 # AsyncFileWriterInterface (ABC, async)
│   │   ├── local_file_system_client.py              # LocalFileSystemClient — sync concrete adapter
│   │   └── async_local_file_system_client.py        # AsyncLocalFileSystemClient — async concrete adapter (aiofiles)
│   ├── __init__.py              # re-exports all public clients
│   └── postgres_client.py       # PostgresClient — generic psycopg wrapper, table-agnostic
├── configs/
│   ├── agent_config.py               # AgentConfig (frozen BaseModel) — re-exported from commons/configs/__init__.py
│   ├── embedding_config.py           # EmbeddingConfig (frozen)
│   └── postgres_connection_config.py # PostgresConnectionConfig (frozen)
├── utils/
│   ├── __init__.py              # re-exports deduplicate
│   └── deduplicate.py           # deduplicate[T](items, key, on_duplicate=None) -> Iterator[T]
└── services/
    ├── __init__.py
    └── embeddings/
        ├── __init__.py              # re-exports Embeddable, Embedded, EmbeddingService
        ├── embeddable.py            # Protocol Embeddable + Embedded (@runtime_checkable)
        └── embedding_service.py     # class EmbeddingService

src/domain/
├── __init__.py
├── entities/
│   ├── __init__.py
│   ├── knowledge/
│   │   ├── __init__.py
│   │   └── knowledge_chunk.py   # KnowledgeChunk — row in knowledge_chunks (+ context: str = "")
│   └── quiz/
│       ├── __init__.py
│       ├── quiz_metadata.py     # QuizMetadata — structured enrichment metadata (NormReferenceDescriberAgent output)
│       └── quiz_question.py     # QuizQuestion — row in quiz_questions (+ quiz_metadata)
└── models/
    ├── __init__.py
    └── knowledge/
        ├── __init__.py
        └── retrieval_result.py  # RetrievalResult — chunk + score (similarity search)
```

## Implemented decisions

- **`UseCase[T_In, T_Out]`** (`commons/use_cases/use_case.py`): generic ABC with
  two type parameters that standardises the contract of stateless components with a
  single operation. Abstract method `execute(request: T_In) -> T_Out`; `__call__`
  is marked `@final` and delegates to `execute` — every `UseCase` is directly
  callable (compatible with `ApplyStep`/`ForEach` that receive a callable). Adopted
  by `EmbeddingService`, `ArticleCleaner`, `ArticleChunker`, `FlattenQuiz`,
  `ToEmbeddableQuiz`, `ContextEnricher`, `ImageDescriptionEnricher`,
  `NormReferenceEnricher`. The public
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
- **`KnowledgeChunk`** (Pydantic, `domain/entities/knowledge/`): `source:
  Literal["cds", "cap"]`, `embedding: list[float] | None = None` (None before
  embedding), `context: str = ""` (LLM context for the article paragraph, DB
  column, default empty string). **DB-write-only** entity: no `embedded_text`
  property — the text to embed is on the same-named property of
  `EmbeddableChunkModel` (intermediate DTO in the ingestor). `KnowledgeChunk`
  satisfies only the `Embedded` protocol (has `embedding`), not `Embeddable`.
- **`QuizQuestion`** (Pydantic, `BaseModel`, `domain/entities/quiz/`): row of
  `quiz_questions` — `number: str`, `question_id: int`, `topic: str`,
  `text: str`, `correct_answer: bool`, `image_filename: str | None = None`,
  `quiz_metadata: QuizMetadata | None = None` (nullable; structured enrichment
  metadata produced by `NormReferenceDescriberAgent`, serialised as JSONB in DB),
  `embedding: list[float] | None = None` (None before embedding, same pattern as
  `KnowledgeChunk`). Property `embedded_text -> str`: returns `f"{topic} {text}"`
  — text prefixed with the question topic, used as embedding input instead of
  `text` alone.
- **`entities/` vs `models/`**: `KnowledgeChunk`, `QuizQuestion`, and
  `QuizMetadata` are domain entities, now in `domain/entities/` (moved from
  `commons/entities/` — Clean Architecture naming: `domain` is the innermost ring).
  `QuizMetadata` is embedded as a JSONB value inside `QuizQuestion` and has no
  independent lifecycle: it is an embedded value object of the `quiz_questions`
  table row, so it belongs alongside `QuizQuestion` in `domain/entities/quiz/`.
  `domain/models/` hosts cross-package domain DTOs that are not DB rows:
  `RetrievalResult` (knowledge retrieval — wraps a `KnowledgeChunk` with a score).
  Ingestor-specific intermediate DTOs (`QuizBankModel`/`QuizBankItemModel`,
  `EnrichedQuizModel`/`EnrichedQuizItemModel`, `EmbeddableQuizModel`,
  `ImageDescription`, renamed in SP04-bis) and `EnrichedArticleModel` (together
  with `ParsedArticleModel` and `EmbeddableChunkModel`) live in
  `guidami_ai_patente_ingestor/models/` because they are ingestor-specific DTOs
  not needed by the FastAPI app.
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
- **`FileRepository[T]`** (`commons/repositories/file_repository/file_repository_protocol.py`,
  `Protocol`): abstract interface following the Dependency Inversion Principle.
  Two methods: `load(file_name) -> T | Sequence[T]` and
  `write(data, file_name) -> None`. The domain depends on this protocol, not on
  the concrete format.
- **`BaseFileRepository[T]`** (`commons/repositories/file_repository/_base_file_repository.py`,
  abstract): shared (de)serialisation logic for Pydantic models, dataclasses, and
  plain dicts. Subclasses implement `_read_raw(path) -> dict | list` and
  `_write_raw(data, path) -> None` for the format-specific I/O.
  - `__init__(base_path, model_class=None)`: resolves and stores the base
    directory; infers `model_class` from the generic parameter if not passed
    explicitly (walks `__orig_bases__` looking for any parameterised
    `BaseFileRepository` subclass and returns the first concrete type argument —
    skipping TypeVars).
  - `get_instance(base_path, model_class)` — classmethod factory; creates a
    typed instance without requiring a named subclass.
  - `load(file_name)`: calls `_read_raw`, then dispatches to `_deserialize_item`
    for dicts or iterates for lists; raises `ValueError` if the content is neither.
  - `write(data)`: serialises via `_serialize_item` and calls `_write_raw`.
  - `_resolve(path)`: joins `base_path / path`; an absolute path argument
    bypasses `base_path` (standard `pathlib` behaviour).
  - Supports Pydantic v2 (`model_validate` / `model_dump`), dataclasses
    (`asdict`), and plain dicts. Unsupported types raise `TypeError`.
- **`JsonRepository[T]`** (`commons/repositories/file_repository/json_repository.py`):
  concrete JSON implementation of `BaseFileRepository[T]`. `_read_raw` raises
  `FileNotFoundError` with the full path; `_write_raw` creates parent directories
  and writes with `ensure_ascii=False, indent=2` to preserve Unicode.
- **`YamlRepository[T]`** (`commons/repositories/file_repository/yaml_repository.py`):
  concrete YAML implementation of `BaseFileRepository[T]` using `yaml.safe_load`
  / `yaml.safe_dump`. Currently used by `BaseAgent.from_yaml` to load
  `AgentConfig` files.
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
  - Methods: `run(request: T_In, images)` (async), `run_sync(request: T_In,
    images)` (sync) and `__call__` (alias for `run_sync`). They extract template
    variables via `request.model_dump()` and pass them to `PromptRenderer.render`.
    Both delegate to `self._agent.run_sync` / `self._agent.run`; return `.output`
    typed as `T_Out`.
  - Factory: `from_yaml(name, repository, output_type) -> BaseAgent[T_In, T_Out]`
    — accepts a pre-constructed `YamlRepository[AgentConfig]` (built by the caller)
    and loads `f"{name}.yaml"` (the `.yaml` extension is appended by `from_yaml`,
    not by the repository). The repository is injected, not created internally —
    aligns with the project DI convention (repositories are constructed at the
    orchestrator level and passed in). Agent subclasses override `from_yaml` with a
    fixed `output_type` and call
    `super().from_yaml(name, repository, output_type=ResponseType)`.
  - Property `core_agent`: exposes `self._agent` to allow
    `with agent.core_agent.override(model=TestModel(...))` in tests.
  Auth via `OPENROUTER_API_KEY` in the environment — never in the YAML or in the code.
- **`BaseFileSystemClient`** (`commons/clients/file_system/_base_file_system_client.py`):
  security mixin — no abstract methods, no I/O. Constructor accepts `base_directory: str | Path`
  and resolves it with `Path.resolve()`. Three layered protected helpers:
  - `_resolve_path(relative_path)` → validates path traversal, raises
    `PermissionError("Path traversal attempt detected.")`, returns the absolute `Path`
    regardless of file existence;
  - `_get_safe_read_path(relative_path)` → calls `_resolve_path` then raises
    `FileNotFoundError` if the file does not exist;
  - `_get_safe_write_path(relative_path)` → calls `_resolve_path` then auto-creates
    parent directories (`mkdir(parents=True, exist_ok=True)`).
  Traversal protection always has precedence — `PermissionError` is raised before any
  I/O error.
- **4 ABC interfaces** (`commons/clients/file_system/interfaces/`): follow Interface
  Segregation — sync and async are separate; read and write are separate.
  - `FileReaderInterface`: `read_text`, `read_bytes`, `read_stream(chunk_size=8192) -> Iterator[bytes]`,
    `exists` (validation — returns `None` on success, raises `FileNotFoundError` if missing);
  - `FileWriterInterface`: `write_text`, `write_bytes`, `write_stream(data: Iterable[bytes])`;
  - `AsyncFileReaderInterface`: async variants; `read_stream` is an async generator declared as
    plain `def` returning `AsyncIterator[bytes]` to avoid ABC/async-generator override mismatch;
  - `AsyncFileWriterInterface`: async variants; `write_stream` accepts `AsyncIterable[bytes]`.
- **`LocalFileSystemClient`** (`commons/clients/file_system/local_file_system_client.py`):
  inherits `BaseFileSystemClient + FileReaderInterface + FileWriterInterface`. Read methods call
  `_get_safe_read_path`; write methods call `_get_safe_write_path`; `exists` delegates to
  `_get_safe_read_path` and discards the return value. Module-level
  `logger = logging.getLogger(__name__)` with f-strings (G004 suppressed globally).
  Unexpected `OSError` is logged at ERROR then re-raised; `PermissionError`/`FileNotFoundError`
  propagate as-is.
- **`AsyncLocalFileSystemClient`** (`commons/clients/file_system/async_local_file_system_client.py`):
  inherits `BaseFileSystemClient + AsyncFileReaderInterface + AsyncFileWriterInterface`. Uses
  `aiofiles` for all async I/O. `async exists` calls `_get_safe_read_path` synchronously (path
  resolution is CPU-bound; no await). Same logging/error pattern as the sync client.
  Both clients are exported from `commons.clients` alongside `PostgresClient` and the embedding
  clients.
- **`deduplicate[T]`** (`commons/utils/deduplicate.py`): generic, order-preserving
  deduplication iterator. Signature: `deduplicate(items: Iterable[T], key:
  Callable[[T], Hashable], on_duplicate: Callable[[T], None] | None = None) ->
  Iterator[T]`. Yields each item the first time its key is seen; subsequent
  duplicates are discarded (calling `on_duplicate` if provided). Exported from
  `commons.utils` via `__all__ = ["deduplicate"]`. Imported by three quiz
  services with `from commons.utils import deduplicate` (absolute import —
  `commons` and `guidami_ai_patente_ingestor` are separate top-level packages).
  Three usage patterns established in the quiz bank:
  1. **List comprehension with `on_duplicate` warning**: `[mapper(item) for item in
     deduplicate(request, key=..., on_duplicate=lambda item: logger.warning(...))]`;
     used in `FlattenQuiz` and `ToEmbeddableQuiz`.
  2. **Generator of pairs** (flatten nested structure before dedup): flatten
     `(sub_q, main_q)` pairs in a generator expression, pass to `deduplicate()`,
     unpack the pair for the mapper call inside the list comprehension; used in
     `FlattenQuiz`.
  3. **Pre-filter generator + `cast`**: `deduplicate((q for q in items if q.image
     is not None), key=...)` to restrict the dedup set to a subset; `cast(str,
     q.image)` inside the loop to satisfy pyright's `str | None` narrowing; used
     in `ImageDescriptionEnricher._describe_questions_with_images`.

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
- `tests/commons/clients/test_file_system_client.py` — 21 unit tests, no `integration`
  marker, all use `tmp_path`. Three test classes: `TestBaseFileSystemClient` (5 tests —
  traversal blocked, valid path resolved, missing file on read, traversal on write,
  auto-mkdir on write); `TestLocalFileSystemClient` (9 tests — text/bytes/stream
  round-trips, UTF-8 with `àèìòù`, missing parent auto-created, overwrite, `exists`
  happy path and both error paths); `TestAsyncLocalFileSystemClient` (7 tests — same
  I/O scenarios async + `exists` error paths). Async tests run via `pytest-asyncio`
  with `asyncio_mode = "auto"`.
- `tests/commons/clients/test_postgres_client.py` — against the compose Postgres
  (no `integration` marker): `truncate`, `execute_many`/`fetch` on
  `knowledge_chunks` (bulk insert + ordered read).
- `tests/domain/entities/knowledge/test_knowledge_chunk.py` — default
  `embedding=None`, default `context=""`. No tests for `embedded_text`
  (`KnowledgeChunk` does not have this property — it is on `EmbeddableChunkModel`).
- `tests/domain/models/knowledge/test_retrieval_result.py` — wrapping
  `KnowledgeChunk` in `RetrievalResult` with `score`.
- `tests/commons/agents/test_agent_config.py` — parsing from YAML dict; defaults
  applied; missing required fields → `ValidationError`; `frozen=True` verifies
  immutability. (`AgentConfig` now lives in `commons/configs/agent_config.py`
  but the tests remain in `tests/commons/agents/`.)
- `tests/commons/agents/test_base_agent.py` — `YamlRepository` raises
  `FileNotFoundError` for missing files and parses valid YAML into `AgentConfig`;
  `PromptRenderer.render` substitutes `$var` placeholders; with `images` the list
  contains `BinaryContent`; `BaseAgent.from_yaml` factory method; missing agent
  file raises `FileNotFoundError`; YAML parameters mapped to `model_settings`
  (`temperature`, `max_tokens`, `timeout`, `_max_output_retries`).
- `tests/commons/repositories/test_file_repository.py` — round-trips for
  `JsonRepository` and `YamlRepository` (single object, list, empty list);
  creates parent directories; preserves UTF-8; `FileNotFoundError` for missing
  files; absolute path bypasses `base_path`; `get_instance` factory; typed
  subclass type inference; untyped subclass raises `TypeError`; Pydantic, dataclass,
  and dict (de)serialisation; unsupported type raises `TypeError`;
  non-dict/non-list content raises `ValueError`.
- `tests/commons/utils/test_deduplicate.py` — 9 unit tests (no `integration`
  marker, no external dependencies): unique items returned in first-occurrence
  order; empty iterable → empty iterator; all-unique passthrough; `on_duplicate`
  called once per duplicate; `on_duplicate=None` does not raise; tuple key;
  return type is `Iterator` (not list); generator as input. Test package mirrors
  `src/` layout (`tests/commons/utils/__init__.py` present).
