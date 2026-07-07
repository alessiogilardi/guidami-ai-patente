---
status: Implemented
effort: L
---
# Integrate File System Client into Repositories

References: `docs/plans/2026-07-04--file-system-client.md` (introduced `LocalFileSystemClient`,
explicitly left repository integration as a non-goal), `docs/plans/2026-07-04--from-yaml-inject-repository.md`
(established the "caller constructs the repository, injects it" pattern this plan extends one level
deeper), `.claude/rules/dependency-injection.md` (constructor argument order convention)

## Context and motivation

`JsonRepository` and `YamlRepository` (`src/commons/repositories/file_repository/`) currently do
their own raw `pathlib`/`json`/`yaml` file I/O: `BaseFileRepository` resolves `base_path` itself
(`Path(base_path).resolve()`) and each subclass's `_read_raw`/`_write_raw` calls `path.read_text()`,
`path.write_text()`, `path.parent.mkdir(...)` directly. This duplicates exactly what
`src/commons/clients/file_system/LocalFileSystemClient` already provides: safe path resolution
anchored to a base directory, path-traversal protection, auto-creation of parent directories on
write, and structured logging.

This plan makes the repositories delegate all disk access to an injected `LocalFileSystemClient`,
so `JsonRepository`/`YamlRepository` become pure serialization logic (encode/decode) and the
file-system concerns (path safety, logging, mkdir) live in one place.

## Non-goals

- `AsyncLocalFileSystemClient` / any async repository variant — `BaseFileRepository` is fully
  synchronous today and has no async consumer; out of scope.
- A new combined interface/Protocol abstracting "something that can read_text and write_text".
  `LocalFileSystemClient` already implements both `FileReaderInterface` and `FileWriterInterface`
  and is the only concrete implementation repositories need; introducing an additional abstraction
  now would be speculative.
- Any change to the public `load`/`write` signatures of `BaseFileRepository` (still take
  `file_name: str | Path`, still return `T | Sequence[T]` / `None`).
- Any change to (de)serialization logic (`_infer_model_class`, `_deserialize_item`, `_serialize_item`).
- Directory listing, deletion, or any capability `LocalFileSystemClient` doesn't already expose.

## Decisions

1. **`BaseFileRepository` stops owning `base_path`; it receives a `LocalFileSystemClient` instead.**
   All path resolution, traversal protection, existence checks, and parent-dir creation move to the
   client. `_read_raw`/`_write_raw` receive `file_name: str | Path` unchanged (no longer a
   pre-resolved absolute `Path`) and pass it straight through to
   `self._file_system_client.read_text(...)` / `.write_text(...)`.

2. **Constructor: `model_class` stays optional and positional, `file_system_client` becomes a
   required keyword-only argument.**
   Per `.claude/rules/dependency-injection.md`, the injected dependency must be last. `model_class`
   must keep its `None` default to preserve the existing type-inference-from-subclass pattern
   (`class Repo(JsonRepository[Model])`, covered by
   `tests/guidami_ai_patente_ingestor/repositories/test_json_repository.py::TestTypeInference`).
   Python forbids a required positional parameter after a defaulted one, so the dependency is
   pushed past a bare `*` into keyword-only territory — still textually last, still required:
   ```python
   def __init__(
       self,
       model_class: type[T] | None = None,
       *,
       file_system_client: LocalFileSystemClient,
   ) -> None: ...

   @classmethod
   def get_instance(cls, model_class: type[T], file_system_client: LocalFileSystemClient) -> Self:
       return cls(model_class, file_system_client=file_system_client)
   ```

3. **Type-hint the dependency as the concrete `LocalFileSystemClient`, not an interface.**
   `BaseFileRepository` is synchronous only; `LocalFileSystemClient` is the sole synchronous,
   local-disk implementation of both `FileReaderInterface` and `FileWriterInterface`. Typing
   against it directly avoids a premature abstraction (see Non-goals #2) while still keeping the
   dependency injected and swappable in principle.

4. **Path-traversal enforcement is a deliberate, intentional behavior tightening.**
   `LocalFileSystemClient` raises `PermissionError` when a resolved path escapes its
   `base_directory`. This removes the current ability to pass an absolute `file_name` that bypasses
   `base_path` entirely (exercised today by
   `tests/commons/repositories/test_file_repository.py::test_absolute_path_bypasses_base_path`).
   That test is rewritten to assert the new `PermissionError` instead of a successful escape — this
   is the security property the client exists to provide, not a regression to preserve.

5. **All production and test call sites construct a `LocalFileSystemClient` explicitly.**
   Every current `JsonRepository(base_path, Model)` / `YamlRepository(base_path, Model)` /
   `.get_instance(base_path, Model)` call becomes
   `JsonRepository(Model, file_system_client=LocalFileSystemClient(base_path))` /
   `.get_instance(Model, LocalFileSystemClient(base_path))`. No helper/factory is introduced for
   this — the construction is a one-liner and call sites already vary in what `base_path` they use.

6. **No hardcoded `"."` — the flow-file root becomes an explicit, overridable config field.**
   `knowledge_flows.py`/`quiz_flows.py` currently call `JsonRepository.get_instance(".", Model)`,
   relying on the process's cwd implicitly. `"."` is replaced by a new `IngestorConfig.project_root:
   Path` field (default `Path(".")`, matching current behavior exactly). Because `IngestorConfig`
   is a `pydantic-settings` `BaseSettings` with `env_nested_delimiter="__"` and a YAML source
   already wired up (`ingestor_config.py:16-22`), the field is automatically overridable via the
   `PROJECT_ROOT` env var or `configs/ingestor_config.yaml` with zero extra plumbing — no manual
   env var reading. `config.agents_dir` is untouched: it already comes from config (not a hardcoded
   literal), so it already satisfies the "explicit path" requirement.

## Open questions / Risks

- **[ACCEPTED, not actioned] `project_root` only anchors two call sites; `agents_dir`/
  `quiz_images_dir` stay independent.**
  What: `IngestorConfig` will have three directory-ish fields after this plan —
  `project_root` (new), `agents_dir`, `quiz_images_dir` — but only `project_root` feeds the
  `JsonRepository.get_instance(...)` calls in the flow files. `agents_dir` and `quiz_images_dir`
  keep resolving relative to the process's cwd, independently of `project_root`.
  Why it matters: if someone overrides `PROJECT_ROOT` expecting to relocate *all* ingestor I/O
  (e.g. to point the whole pipeline at a mounted data volume in a container), `agents_dir` silently
  won't follow — it still resolves relative to cwd, which could point at a config directory that
  doesn't exist under the new root. This is a latent footgun, not a bug introduced by this plan
  (the same disconnect exists today between `"."` and `agents_dir`), but this plan is the first time
  `project_root` becomes a named, discoverable field, which raises the chance someone treats it as
  "the" root.
  Checked while re-scoping: `quiz_images_dir` isn't even consumed by a repository — it's passed
  directly to `ImageDescriptionEnricher` (`quiz_flows.py:234`), a component this plan doesn't touch.
  Joining it under `project_root` would mean editing `ImageDescriptionEnricher`'s path handling too,
  which is scope creep for this plan.
  Resolution: staying out of scope. Do not join `agents_dir`/`quiz_images_dir` under `project_root`
  here — unifying all three into one root is a separate, bigger config decision (changes
  `agents_dir`'s default, `ImageDescriptionEnricher`'s path handling, and every place that reads
  either field) that hasn't been requested. If you want it, it should be its own plan.

- **[VERIFIED LOW-RISK] `PROJECT_ROOT` is a generic env var name.**
  What: `IngestorConfig` fields are matched by bare name via `pydantic-settings`, so the new field
  is overridable via a plain `PROJECT_ROOT` env var, with no project-specific prefix.
  Why it mattered: `PROJECT_ROOT` is a common convention in other tools/CI runners; if the execution
  environment already exported a `PROJECT_ROOT` for unrelated reasons, `IngestorConfig` would
  silently pick it up and redirect all `JsonRepository.get_instance(...)` I/O.
  Checked now: `grep`'d `.env.example` and the repo for `PROJECT_ROOT` — no existing usage anywhere,
  and there's no CI workflow (`.github/workflows/` doesn't exist) that could inject it. Residual risk
  is limited to whatever shell the ingestor is eventually run in outside this repo (e.g. a future
  Docker base image with its own `PROJECT_ROOT`) — unverifiable until that environment exists.
  Resolution: no action now. If it ever collides, rename the field/env var then — not worth
  preemptively prefixing every `IngestorConfig` field for a hypothetical.

- **[RESOLVED — non-issue] Client construction is cheap and stateless — no caching needed.**
  What: `LocalFileSystemClient(config.project_root)` is constructed fresh at every flow-function
  call in `knowledge_flows.py`/`quiz_flows.py`, mirroring the current
  `JsonRepository.get_instance(".", ...)` pattern, which already re-resolves its base path per call.
  Why it doesn't matter: each construction only does `Path(base_directory).resolve()` — no I/O, no
  connection, no allocation worth amortizing. No task item needed; noted so a future reviewer
  doesn't mistake the repeated construction for an oversight.

- **[RESOLVED — confirmed by reading the tests] `MagicMock(spec=JsonRepository)` tests are
  unaffected.**
  What: `test_load_json_step.py`/`test_write_json_step.py` build their fake repository with
  `MagicMock(spec=JsonRepository)`.
  Why it doesn't matter: `spec=` only constrains which *attributes* the mock exposes (via
  introspecting the class), it never calls `__init__` — so changing `JsonRepository.__init__`'s
  signature (Decision 2) cannot break these tests. Confirmed by reading both files during scoping;
  no task item exists for them for this reason.

- **[DEFERRED — future plan] `ImageDescriptionEnricher` and `PromptRenderer` read image files
  directly off disk, bypassing any file system client.**
  What: `ImageDescriptionEnricher._describe_image`
  (`src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py:63`) calls
  `path.exists()` on a raw `Path` built from `self._images_dir / image`; `PromptRenderer.render`
  (`src/commons/agents/base_agent.py:48`) calls `img.read_bytes()` directly on the image `Path`
  handed to it. Neither goes through `LocalFileSystemClient` — no path-traversal protection, no
  centralized logging, same duplication this plan removes from the repositories.
  Why it's deferred, not fixed here: this plan's scope is `BaseFileRepository`/`JsonRepository`/
  `YamlRepository` (JSON/YAML persistence). `ImageDescriptionEnricher` and `PromptRenderer` are a
  different consumer shape — they need `read_bytes`/`exists` on arbitrary image paths handed in at
  call time, not a `(base_path, model_class)`-style repository. Wiring them to
  `LocalFileSystemClient`/`FileReaderInterface` is a legitimate follow-up but touches
  `RoadSignDescriberAgent`'s and `BaseAgent`'s constructors and call sites — a separate plan.
  Resolution: not actioned in this plan. Left here so it isn't lost, and so a future plan can cite
  this as the concrete starting point (exact file:line references above).

## Implementation tasks

### 1. `BaseFileRepository` — inject `LocalFileSystemClient`, drop `base_path`/`_resolve`

File: `src/commons/repositories/file_repository/_base_file_repository.py`

- Add `from commons.clients.file_system import LocalFileSystemClient`.
- Replace `__init__(self, base_path: str | Path, model_class: type[T] | None = None)` with the
  signature in Decision 2; store `self._file_system_client = file_system_client`; drop
  `self._base_path`.
- Update `get_instance` per Decision 2.
- Remove `_resolve` (no longer needed — the client resolves paths).
- Change abstract method signatures to take `file_name: str | Path` (rename the `path` parameter
  to make clear it's no longer a resolved absolute path):
  ```python
  @abstractmethod
  def _read_raw(self, file_name: str | Path) -> dict | list: ...

  @abstractmethod
  def _write_raw(self, data: dict | list, file_name: str | Path) -> None: ...
  ```
- `load`/`write` bodies: replace `self._resolve(file_name)` with `file_name` passed directly to
  `_read_raw`/`_write_raw`.
- Leave `_infer_model_class`, `_deserialize_item`, `_serialize_item` untouched.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- No dedicated test file for `BaseFileRepository` alone — behavior is exercised through
  `JsonRepository`/`YamlRepository` tests (task 3).

### 2. `JsonRepository` / `YamlRepository` — delegate I/O to the client

Files: `src/commons/repositories/file_repository/json_repository.py`,
`src/commons/repositories/file_repository/yaml_repository.py`

- `JsonRepository._read_raw`: `return json.loads(self._file_system_client.read_text(file_name))`.
- `JsonRepository._write_raw`:
  `self._file_system_client.write_text(file_name, json.dumps(data, ensure_ascii=False, indent=2))`.
- `YamlRepository._read_raw`: `return yaml.safe_load(self._file_system_client.read_text(file_name))`.
- `YamlRepository._write_raw`:
  `self._file_system_client.write_text(file_name, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))`.
- Remove now-unused imports (`Path` stays for type hints; drop nothing else that's still referenced).

**Tests** (intent, not contract):
- No new test files — existing round-trip tests in task 3 cover this directly.

### 3. Update `tests/commons/repositories/test_file_repository.py`

- Add `from commons.clients.file_system import LocalFileSystemClient`.
- Every `JsonRepository(tmp_path, Model)` / `YamlRepository(tmp_path, Model)` /
  `.get_instance(tmp_path, Model)` call becomes
  `JsonRepository(Model, file_system_client=LocalFileSystemClient(tmp_path))` (same for Yaml and
  `get_instance`).
- `TestTypeInference::test_infer_from_typed_subclass` and `test_no_type_param_raises_type_error`:
  update `TypedRepo(tmp_path)` / `UntypedRepo(tmp_path)` to
  `TypedRepo(file_system_client=LocalFileSystemClient(tmp_path))` (model_class omitted, inferred).
- `test_absolute_path_bypasses_base_path` (Decision 4): rewrite to construct the repository with
  `base_path=tmp_path / "base"`, attempt to write to an absolute path under `tmp_path / "elsewhere"`,
  and assert `pytest.raises(PermissionError, match="[Tt]raversal")`. Rename to
  `test_absolute_path_outside_base_raises_permission_error`.
- `test_creates_parent_directories` (Json and Yaml): unaffected in behavior — `nested` stays inside
  `tmp_path` (the client's `base_directory`), so no traversal is triggered; only the constructor
  call changes.

**Tests** (intent, not contract):
- Modify: all tests in this file per above — mechanical constructor-call update plus the one
  rewritten test.

### 4. Update `tests/guidami_ai_patente_ingestor/repositories/test_json_repository.py`

- Add `from commons.clients.file_system import LocalFileSystemClient`.
- Every `JsonRepository.get_instance(tmp_path, model_cls)` / `.get_instance(FIXTURES_DIR, Model)`
  becomes `JsonRepository.get_instance(model_cls, LocalFileSystemClient(tmp_path))` /
  `LocalFileSystemClient(FIXTURES_DIR)`.

**Tests** (intent, not contract):
- Modify: all `get_instance` call sites in this file — mechanical update, no behavior change
  (all paths used are already relative and inside the base dir).

### 5. Update agent `YamlRepository` construction across tests

Files:
- `tests/commons/agents/test_base_agent.py`
- `tests/commons/agents/test_base_agent_from_yaml_injection.py`
- `tests/guidami_ai_patente_ingestor/agents/test_subagents_from_yaml_injection.py`
- `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py`
- `tests/guidami_ai_patente_ingestor/agents/test_article_contextualizer_agent.py`

Every `YamlRepository(agents_dir, AgentConfig)` becomes
`YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(agents_dir))`. Add the
`LocalFileSystemClient` import where missing.

**Tests** (intent, not contract):
- Modify: all `YamlRepository(agents_dir, AgentConfig)` construction sites in the five files above
  — mechanical update, no behavioral assertions change.

### 6. Update `test_article_chunker.py` / `test_article_cleaner.py` fixtures

Files:
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_chunker.py`
- `tests/guidami_ai_patente_ingestor/services/knowledge/test_article_cleaner.py`

`JsonRepository.get_instance(FIXTURES_DIR, ParsedArticleModel)` becomes
`JsonRepository.get_instance(ParsedArticleModel, LocalFileSystemClient(FIXTURES_DIR))`.

**Tests** (intent, not contract):
- Modify: module-level `_article_repo` construction and the one in-test construction —
  mechanical update.

### 7. Add `IngestorConfig.project_root` field

File: `src/guidami_ai_patente_ingestor/configs/ingestor_config.py`

Add `project_root: Path = Path(".")` next to `agents_dir`/`quiz_images_dir` (same style: bare
`Path` field, no `Field(...)` needed since there's no extra metadata). No changes to
`settings_customise_sources` — the existing env/YAML precedence chain applies automatically.

**Tests** (intent, not contract):
- `tests/guidami_ai_patente_ingestor/configs/` — if a config test asserts the full set of
  `IngestorConfig` fields/defaults, add `project_root` to it; otherwise no test change needed
  (default-value fields aren't required to have dedicated coverage per existing convention — check
  the directory before assuming either way).

### 8. Update production flow call sites

Files:
- `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py`
- `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`

Add `from commons.clients.file_system import LocalFileSystemClient`. Every
`JsonRepository.get_instance(".", Model)` becomes
`JsonRepository.get_instance(Model, LocalFileSystemClient(config.project_root))`; every
`YamlRepository(config.agents_dir, AgentConfig)` becomes
`YamlRepository(AgentConfig, file_system_client=LocalFileSystemClient(config.agents_dir))`.

**Tests** (intent, not contract):
- `tests/.../test_knowledge_preparation_flows.py` and `test_quiz_preparation_flows_v2.py` patch
  `from_yaml`/repository construction by name — confirm no direct assertions on constructor
  arguments exist before assuming no change is needed; update only if a test asserts call arguments.

## Definition of Done

Variable block (plan-specific):

- [x] `grep -rn "base_path" src/commons/repositories/file_repository/` returns no hits
- [x] `grep -rn "_resolve\b" src/commons/repositories/file_repository/_base_file_repository.py` returns no hits
- [x] `grep -rln "LocalFileSystemClient" src/commons/repositories/file_repository/_base_file_repository.py src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py` — all three files present
- [x] `grep -rn "JsonRepository([^M]*,\s*[A-Z]" tests/ src/ | grep -v file_system_client` returns no hits (no remaining positional `base_path`-first construction)
- [x] `grep -n "project_root" src/guidami_ai_patente_ingestor/configs/ingestor_config.py` — field present
- [x] `grep -n 'LocalFileSystemClient("\.")' src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py` returns no hits (no hardcoded `"."`)
- [x] `uv run pytest tests/commons/repositories/test_file_repository.py tests/guidami_ai_patente_ingestor/repositories/test_json_repository.py -v` green
- [x] `grep -n "test_absolute_path" tests/commons/repositories/test_file_repository.py` shows the renamed `test_absolute_path_outside_base_raises_permission_error`

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests) — 319 passed
- [x] `uv run pyright` clean — 0 errors, 0 warnings
- [x] `uv run ruff check src tests` clean on every file this plan touched (repo-wide, 10 pre-existing violations remain in `src/commons/repositories/__init__.py` and `norm_reference_describer_response.py`, both untouched by this plan and predating it — confirmed via `git log`)
- [x] Agent `doc-architect` invoked (if available)
- [x] Plan updated to `status: Implemented`
