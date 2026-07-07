---
status: Implemented
effort: L
---
# Wire Image Reading To File System Client

References: `docs/plans/2026-07-06--integrate-file-system-client-into-repositories.md` (introduced
the `LocalFileSystemClient`/`FileReaderInterface` injection pattern this plan extends to a
different consumer shape; its "Open questions / Risks" section explicitly deferred this exact work
with file:line references), `.claude/rules/dependency-injection.md` (constructor argument order
convention)

## Context and motivation

`ImageDescriptionEnricher._describe_image`
(`src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py:63`) calls
`path.exists()` on a raw `Path` built from `self._images_dir / image`, and `PromptRenderer.render`
(`src/commons/agents/base_agent.py:48`) calls `img.read_bytes()` directly on the image `Path` handed
to it. Neither goes through `LocalFileSystemClient`/`FileReaderInterface` — no path-traversal
protection, no centralized logging, and the same base-path-joining duplication the sibling plan
already removed from `JsonRepository`/`YamlRepository`.

This plan wires both consumers to `FileReaderInterface` (the read-only interface already defined in
`src/commons/clients/file_system/interfaces/file_reader.py`, whose own docstring calls out ISP:
"consumers that only need to read files depend on this interface alone"). `LocalFileSystemClient` is
the concrete implementation, anchored at `IngestorConfig.quiz_images_dir`, constructed once per flow
run and shared between `RoadSignDescriberAgent` and `ImageDescriptionEnricher` — mirroring the
existing `LocalFileSystemClient(config.agents_dir)` pattern already used for `agents_repository` in
`quiz_flows.py`.

`RoadSignDescriberAgent` is confirmed (by reading `src/guidami_ai_patente_ingestor/agents/`) to be
the only `BaseAgent` subclass that ever passes `images=`; `ArticleContextualizerAgent` and
`NormReferenceDescriberAgent` never do. The file reader is therefore wired as an **optional**
dependency on `BaseAgent`/`PromptRenderer` (default `None`), not a required one — see Decision 1.

## Non-goals

- `AsyncLocalFileSystemClient` / async image reading. `PromptRenderer.render` is called
  synchronously from both `BaseAgent.run` (async) and `BaseAgent.run_sync` today; this plan changes
  *what* reads the bytes, not the sync/async shape of the call. No regression, not addressed here.
- Any change to `ArticleContextualizerAgent` or `NormReferenceDescriberAgent` — neither passes
  `images=`, so neither needs a `file_reader`; their constructors, `from_yaml` overrides, and tests
  are untouched.
- Any change to `FileWriterInterface` usage — images are read-only in this flow, only
  `FileReaderInterface` is needed.
- Unifying `quiz_images_dir` and `agents_dir` under one root — out of scope per the deferred note in
  the sibling plan; this plan uses `quiz_images_dir` exactly as it exists today.
- Any change to the `(image, topic, text)` dedup key or dedup logic in `ImageDescriptionEnricher`.
- Any change to `BaseFileRepository`/`JsonRepository`/`YamlRepository` — already handled by the
  sibling plan, whose code is already present in `_base_file_repository.py` and `quiz_flows.py`.

## Decisions

1. **`file_reader` is an optional constructor dependency on `PromptRenderer`/`BaseAgent`, not a
   required one.**
   `PromptRenderer.__init__(self, template_str: str, file_reader: FileReaderInterface | None = None)`
   and `BaseAgent.__init__(self, config: AgentConfig, output_type: type[T_Out], file_reader:
   FileReaderInterface | None = None)` both default to `None`. `BaseAgent.from_yaml` gains the same
   optional trailing parameter and forwards it to `cls(config, output_type, file_reader)`.
   This is a deliberate, narrow deviation from the "dependencies are always injected, never
   optional" convention: two of the three concrete agents (`ArticleContextualizerAgent`,
   `NormReferenceDescriberAgent`) never pass `images=` and would otherwise be forced to construct
   and thread through a `LocalFileSystemClient` they never use — pure blast radius with no behavior
   change. `PromptRenderer.render` raises `ValueError` if `images` is non-empty and no `file_reader`
   was configured, so a future agent that starts passing images without wiring a reader fails fast
   at first use rather than silently reading nothing.

2. **`RoadSignDescriberAgent.from_yaml` narrows `file_reader` to required.**
   ```python
   @classmethod
   def from_yaml(  # type: ignore[override]
       cls, name: str, repository: YamlRepository, file_reader: FileReaderInterface
   ) -> "RoadSignDescriberAgent":
       return super().from_yaml(name, RoadSignDescriberResponse, repository, file_reader)  # type: ignore[return-value]
   ```
   Same pattern already used for narrowing `output_type` in this class's existing override — this
   subclass always needs images, so its own factory makes the dependency mandatory even though the
   base class keeps it optional.

3. **`ImageDescriptionEnricher` drops `images_dir: Path`, takes `file_reader: FileReaderInterface`
   instead.**
   ```python
   def __init__(
       self, road_sign_describer: RoadSignDescriberAgent, file_reader: FileReaderInterface
   ) -> None: ...
   ```
   Both remaining constructor parameters are injected collaborators (agent + client); per
   `.claude/rules/dependency-injection.md`'s guidance for two dependencies ("both go at the end...in
   whatever relative order reads best"), `road_sign_describer` stays first (the enricher's primary
   collaborator, matching its current position) and `file_reader` last.

4. **`_describe_image` passes the bare relative image name through, not a resolved absolute
   `Path`.**
   `image = cast(str, q.image)` is used directly — no more `self._images_dir / image` join. The
   existence check becomes:
   ```python
   try:
       self._file_reader.exists_or_raise(image)
   except (FileNotFoundError, PermissionError):
       logger.warning("Image file not found, skipping description: %s", image)
       return None
   ```
   `PermissionError` (path-traversal, raised by `BaseFileSystemClient._resolve_path`) is handled the
   same as a missing file — skip and warn — rather than left to propagate as an unhandled crash.
   `images=(Path(image),)` is then passed to `run_sync` unchanged in type (`tuple[Path, ...]`) but
   now relative, resolved by the same `file_reader` (same base directory) inside
   `PromptRenderer.render`.

5. **One `LocalFileSystemClient(config.quiz_images_dir)` is shared by both consumers in
   `quiz_flows.py`.**
   Constructed once and passed to both `RoadSignDescriberAgent.from_yaml(...)` and
   `ImageDescriptionEnricher(...)`, exactly mirroring the existing
   `LocalFileSystemClient(config.agents_dir)` reused for `agents_repository` in the same file.

## Open questions / Risks

- **[RESOLVED — confirmed by reading the test] `test_quiz_preparation_flows_v2.py` needs no
  changes.**
  What: this file patches `RoadSignDescriberAgent.from_yaml` wholesale via
  `patch.object(RoadSignDescriberAgent, "from_yaml", return_value=_patched_describer())`, and its
  `_patched_describer()` helper builds `MagicMock(spec=RoadSignDescriberAgent)`.
  Why it doesn't matter: `patch.object(..., return_value=...)` replaces the callable entirely,
  ignoring its real signature; `MagicMock(spec=...)` only constrains which *attributes* the mock
  exposes, it never calls `__init__`. Changing `from_yaml`'s and `ImageDescriptionEnricher.__init__`'s
  signatures cannot break this file. Confirmed by reading it during scoping — no task item exists
  for it for this reason.

- **[RESOLVED during implementation] `test_subagents_from_yaml_injection.py` also calls
  `RoadSignDescriberAgent.from_yaml` without a `file_reader`.**
  What: this scoping pass checked `test_road_sign_describer_agent.py` and
  `test_quiz_preparation_flows_v2.py` for `RoadSignDescriberAgent.from_yaml` call sites but missed
  `test_subagents_from_yaml_injection.py:48`, which calls it with only `repository=` and no
  `file_reader`. Decision 2 (required `file_reader`) breaks this call with a `TypeError`.
  Resolution: added to Task 3's test list — the call becomes
  `RoadSignDescriberAgent.from_yaml("road_sign_describer", repository=repository,
  file_reader=LocalFileSystemClient(agents_dir))`, reusing the test's existing `agents_dir`. Found
  by `python-developer` running the full `uv run pytest` suite (not just the DoD's targeted test
  files), which is exactly why the Fixed-block DoD requires the full suite green, not just the
  variable block's targeted run.

- **[ACCEPTED, not actioned] Pre-existing TOCTOU gap between the existence check and the actual
  read.**
  What: `_describe_image` calls `self._file_reader.exists_or_raise(image)` and, if it passes, later
  triggers a separate `self._file_reader.read_bytes(...)` call deep inside
  `PromptRenderer.render` (via `run_sync`). The file could disappear between the two calls.
  Why it's not addressed: this gap already exists today (`path.exists()` then later
  `img.read_bytes()`) — this plan changes *what* performs each check/read, not the two-step shape.
  The broad `except Exception` around `run_sync` in `_describe_image` already catches a
  `FileNotFoundError` raised by the later read and logs+skips, so behavior is unchanged.

## Implementation tasks

### 1. `PromptRenderer` — read images via an injected `FileReaderInterface`

File: `src/commons/agents/base_agent.py`

- Add `from commons.clients import FileReaderInterface` (already re-exported from
  `commons/clients/__init__.py`, per the project's import convention of using package re-exports
  over internal file paths).
- `__init__(self, template_str: str, file_reader: FileReaderInterface | None = None) -> None`:
  store `self._file_reader = file_reader` alongside `self._template`.
- `render`: replace `BinaryContent(data=img.read_bytes(), media_type=media_type)` with
  `BinaryContent(data=self._file_reader.read_bytes(img), media_type=media_type)`. Before the loop,
  if `images` is non-empty and `self._file_reader is None`, raise
  `ValueError("images were provided but no file_reader was configured")`.
- Update the docstring's `images` param description: paths are now resolved relative to
  `file_reader`'s base directory, not assumed-valid absolute paths.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Modify: `tests/commons/agents/test_base_agent.py::test_prompt_renderer_returns_list_with_binary_content_for_images`
  — construct `PromptRenderer("Descrivi.", LocalFileSystemClient(tmp_path))`, write the image at
  `tmp_path / "stop.jpg"`, pass `images=(Path("stop.jpg"),)` (relative).
- Add: a test asserting `PromptRenderer(...).render({}, images=(Path("x.jpg"),))` raises `ValueError`
  when constructed without a `file_reader`.

### 2. `BaseAgent` — thread the optional `file_reader` through to `PromptRenderer`

File: `src/commons/agents/base_agent.py`

- `__init__(self, config: AgentConfig, output_type: type[T_Out], file_reader: FileReaderInterface | None = None) -> None`:
  pass `file_reader` into `PromptRenderer(config.user, file_reader)`.
- `from_yaml(cls, name: str, output_type: type[T_Out], repository: YamlRepository, file_reader: FileReaderInterface | None = None) -> "BaseAgent[T_In, T_Out]"`:
  forward `file_reader` to `cls(config, output_type, file_reader)`.

**Tests** (intent, not contract):
- No changes needed to existing `BaseAgent`/`from_yaml` tests that don't pass images — `file_reader`
  defaults to `None` and behavior is unchanged.

### 3. `RoadSignDescriberAgent` — require `file_reader` in its `from_yaml` override

File: `src/guidami_ai_patente_ingestor/agents/road_sign_describer_agent.py`

- Add `from commons.clients import FileReaderInterface` import.
- `from_yaml(cls, name: str, repository: YamlRepository, file_reader: FileReaderInterface) -> "RoadSignDescriberAgent"`:
  forward to `super().from_yaml(name, RoadSignDescriberResponse, repository, file_reader)` per
  Decision 2.

**Tests** (intent, not contract):
- Modify: all four tests in `tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py`
  — construct `agent = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_dir,
  LocalFileSystemClient(tmp_path))`, keep writing the image file under `tmp_path`, but pass
  `images=(Path("stop.jpg"),)` (relative) to `run_sync`/`renderer.render` instead of the absolute
  `img` path. Add the `LocalFileSystemClient` import.
- Modify: `tests/guidami_ai_patente_ingestor/agents/test_subagents_from_yaml_injection.py::test_road_sign_describer_from_yaml_accepts_repository`
  (line 48) — found missing during implementation (not caught during scoping, unlike the sibling
  `test_quiz_preparation_flows_v2.py` check in "Open questions / Risks"). This test also calls
  `RoadSignDescriberAgent.from_yaml("road_sign_describer", repository=repository)` without a
  `file_reader`, which breaks once Decision 2 makes it required. Fix:
  `RoadSignDescriberAgent.from_yaml("road_sign_describer", repository=repository,
  file_reader=LocalFileSystemClient(agents_dir))`, reusing the `agents_dir`/`LocalFileSystemClient`
  already constructed in that test. The other two tests in this file
  (`ArticleContextualizerAgent`/`NormReferenceDescriberAgent`) are untouched — neither needs a
  `file_reader`.

### 4. `ImageDescriptionEnricher` — replace `images_dir` with an injected `file_reader`

File: `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py`

- Add `from commons.clients import FileReaderInterface` import; keep the `Path` import —
  `images=(Path(image),)` in `_describe_image` still needs it.
- `__init__(self, road_sign_describer: RoadSignDescriberAgent, file_reader: FileReaderInterface) -> None`
  per Decision 3; store `self._file_reader = file_reader`, drop `self._images_dir`.
- `_describe_image`: per Decision 4, drop the `self._images_dir / image` join; replace the
  `path.exists()` check with the `try/except (FileNotFoundError, PermissionError)` block calling
  `self._file_reader.exists_or_raise(image)`; pass `images=(Path(image),)` to `run_sync` (relative,
  not pre-joined).
- Update the module's `logger.warning` calls that currently interpolate `path` to interpolate
  `image` instead (the resolved absolute path is no longer available at this layer).

**Tests** (intent, not contract):
- Modify: every `ImageDescriptionEnricher(tmp_path, describer)` construction in
  `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py`
  becomes `ImageDescriptionEnricher(describer, LocalFileSystemClient(tmp_path))`. Add the
  `LocalFileSystemClient` import. Existing image files continue to be written under `tmp_path`
  (unchanged) since that's the client's base directory.
- Add: a test with `image="../outside.jpeg"` (or another path escaping `tmp_path`) asserting the
  question is skipped with a warning logged and `describer.run_sync` not called (the
  `PermissionError` branch), analogous to the existing `test_enrich_missing_file_skips_and_warns`.

### 5. `quiz_flows.py` — construct and share one `LocalFileSystemClient` for images

File: `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`

- Per Decision 5, construct `images_file_reader = LocalFileSystemClient(config.quiz_images_dir)`
  once, near the existing `agents_repository = YamlRepository(AgentConfig,
  file_system_client=LocalFileSystemClient(config.agents_dir))` line.
- `describer = RoadSignDescriberAgent.from_yaml("road_sign_describer", agents_repository,
  images_file_reader)`.
- `ImageDescriptionEnricher(describer, images_file_reader)` (replaces
  `ImageDescriptionEnricher(config.quiz_images_dir, describer)`).

**Tests** (intent, not contract):
- No changes: `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py`
  patches `RoadSignDescriberAgent.from_yaml` wholesale and never asserts constructor arguments — see
  the resolved open question above.

## Definition of Done

Variable block (plan-specific):

- [x] `grep -n "img.read_bytes()" src/commons/agents/base_agent.py` returns no hits
- [x] `grep -n "self._file_reader.read_bytes" src/commons/agents/base_agent.py` — present
- [x] `grep -n "images_dir" src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py` returns no hits
- [x] `grep -n "file_reader: FileReaderInterface" src/commons/agents/base_agent.py src/guidami_ai_patente_ingestor/agents/road_sign_describer_agent.py src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py` — present in all three files
- [x] `grep -n "LocalFileSystemClient(config.quiz_images_dir)" src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py` — present
- [x] `grep -n "exists_or_raise" src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py` — present
- [x] `uv run pytest tests/commons/agents/test_base_agent.py tests/guidami_ai_patente_ingestor/agents/test_road_sign_describer_agent.py tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py -v` green

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests) — 321 passed
- [x] `uv run pyright` clean — 0 errors, 0 warnings
- [x] `uv run ruff check src tests` clean
- [x] Agent `doc-architect` invoked (if available)
- [x] Plan updated to `status: Implemented`
