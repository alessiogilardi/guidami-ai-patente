---
status: Archived
effort: L
---
# File System Client

_Archived: fully implemented and shipped (see DoD below); kept for historical reference. Superseded
in scope by [Integrate File System Client into Repositories](2026-07-06--integrate-file-system-client-into-repositories.md),
which wired this client into the repository layer._

References: `file_system_client.md` (reference design at repo root)

## Context and motivation

The `commons` package has no centralized file I/O abstraction. Raw `pathlib.Path` calls are
scattered wherever file access is needed, with no consistent path-security enforcement, no
logging, and no mockable boundary.

This plan introduces `src/commons/clients/file_system/` — a minimal, safe client that provides
sync and async read/write operations anchored to a configurable base directory. The reference
design is `file_system_client.md`; this plan adapts it to project conventions (English, one
class per file, stdlib logging with f-strings, Google docstrings) and extends it with write
operations. No integration with existing repositories or services is in scope here.

## Non-goals

- Directory listing, stat/metadata operations (only safe-access validation via `exists()` is in scope)
- File deletion, move, or copy operations
- File watching or change notification
- A Pydantic config class (base_directory is injected directly into the constructor)
- Integration with existing repositories, services, or pipelines
- OpenTelemetry or any external tracing library

## Decisions

**Package layout — 4 ABCs in an `interfaces/` sub-folder**
Follows Interface Segregation Principle: consumers that only read depend only on
`FileReaderInterface`; consumers that only write depend only on `FileWriterInterface`.
Mirrors the `services/embeddings/protocols/` pattern already in the codebase.

```
src/commons/clients/file_system/
├── __init__.py
├── _base_file_system_client.py
├── interfaces/
│   ├── __init__.py
│   ├── file_reader.py
│   ├── file_writer.py
│   ├── async_file_reader.py
│   └── async_file_writer.py
├── local_file_system_client.py
└── async_local_file_system_client.py
```

**Security model — always active, non-configurable**
`BaseFileSystemClient` resolves `base_directory` at construction with `Path.resolve()`.
Three protected helpers, layered on top of each other:
- `_resolve_path(path)` → resolves path, validates no path traversal; raises `PermissionError("Path traversal attempt detected.")`; returns the absolute `Path` regardless of existence
- `_get_safe_read_path(path)` → calls `_resolve_path` then raises `FileNotFoundError` if file does not exist
- `_get_safe_write_path(path)` → calls `_resolve_path` then auto-creates parent dirs (`mkdir(parents=True, exist_ok=True)`)

`exists()` in concrete classes calls `_get_safe_read_path(path)` — traversal raises `PermissionError` first (precedence); missing file raises `FileNotFoundError`. Returns `None` on success (the file exists and is safely accessible). This is a validation method, not a boolean probe.

**Logging — stdlib f-strings**
Module-level `logger = logging.getLogger(__name__)` in each concrete class.
G004 (logging-fstring-interpolation) is already globally suppressed in `pyproject.toml`.
Log levels: DEBUG for operation start/end, WARNING for path traversal, ERROR for unexpected I/O errors.
Stream methods log file open and close only — not per-chunk.

**Async backend — `aiofiles`**
`AsyncLocalFileSystemClient` uses `aiofiles` for non-blocking I/O. Requires `uv add aiofiles`.

**Async test runner — `pytest-asyncio`**
Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`. Requires `uv add --dev pytest-asyncio`
and adding `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` in `pyproject.toml`.

## Open questions / Risks

None — all design decisions confirmed with user before scaffolding.

## Implementation tasks

### 1. Add dependencies and configure async test runner

Run `uv add aiofiles` and `uv add --dev pytest-asyncio`.
Add `asyncio_mode = "auto"` under `[tool.pytest.ini_options]` in `pyproject.toml`.

**Tests**: none for this step.

### 2. Create `BaseFileSystemClient`

Create `src/commons/clients/file_system/` with empty `__init__.py`.
Create `src/commons/clients/file_system/_base_file_system_client.py`:

```python
class BaseFileSystemClient:
    def __init__(self, base_directory: str | Path) -> None: ...
    def _resolve_path(self, relative_path: str | Path) -> Path: ...
    def _get_safe_read_path(self, relative_path: str | Path) -> Path: ...
    def _get_safe_write_path(self, relative_path: str | Path) -> Path: ...
```

Google-style English docstrings. No abstract methods.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `TestBaseFileSystemClient::test_resolve_path_traversal_raises_permission_error`
- `TestBaseFileSystemClient::test_resolve_valid_path_returns_absolute_path`
- `TestBaseFileSystemClient::test_read_nonexistent_file_raises_file_not_found`
- `TestBaseFileSystemClient::test_write_path_traversal_raises_permission_error`
- `TestBaseFileSystemClient::test_write_missing_parents_created_automatically`

### 3. Create four ABC interfaces

Create `src/commons/clients/file_system/interfaces/` with `__init__.py` re-exporting all four.
One file per ABC:

- `file_reader.py` → `FileReaderInterface(ABC)` with `read_text`, `read_bytes`, `read_stream`, `exists`
- `file_writer.py` → `FileWriterInterface(ABC)` with `write_text`, `write_bytes`, `write_stream`
- `async_file_reader.py` → `AsyncFileReaderInterface(ABC)` — async variants of reader methods including `exists`
- `async_file_writer.py` → `AsyncFileWriterInterface(ABC)` — async variants, `AsyncIterable[bytes]`

Signatures:
```python
# sync reader
def read_text(self, path: str | Path, encoding: str = "utf-8") -> str: ...
def read_bytes(self, path: str | Path) -> bytes: ...
def read_stream(self, path: str | Path, chunk_size: int = 8192) -> Iterator[bytes]: ...
def exists(self, path: str | Path) -> None: ...  # raises PermissionError (traversal) or FileNotFoundError (missing)

# sync writer
def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> None: ...
def write_bytes(self, path: str | Path, data: bytes) -> None: ...
def write_stream(self, path: str | Path, data: Iterable[bytes]) -> None: ...
```
Async variants replace `def` with `async def` and stream types with `AsyncIterator`/`AsyncIterable`.
`async exists` in `AsyncFileReaderInterface` is `async def exists(self, path: str | Path) -> None`. Path resolution is sync (`_get_safe_read_path`), so no `await` is needed internally, but the method is declared `async` for interface consistency. Raises `PermissionError` on traversal (precedence), then `FileNotFoundError` if missing.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
No separate tests — interfaces are validated implicitly by concrete class tests.

### 4. Implement `LocalFileSystemClient` (sync)

Create `src/commons/clients/file_system/local_file_system_client.py`:

```python
class LocalFileSystemClient(BaseFileSystemClient, FileReaderInterface, FileWriterInterface):
    ...
```

All seven methods implemented with stdlib `pathlib` / `open()`.
Read methods and `exists` call `_resolve_path` or `_get_safe_read_path` as appropriate;
write methods call `_get_safe_write_path`.
`exists(path)` → delegates to `_get_safe_read_path(path)` and discards the returned path. Raises `PermissionError` on traversal (precedence); raises `FileNotFoundError` if file is missing; returns `None` if file exists and is safely accessible.
Module-level `logger = logging.getLogger(__name__)`.

Error handling: `PermissionError` and `FileNotFoundError` propagate as-is after WARNING/DEBUG log;
unexpected `OSError` logged at ERROR level then re-raised.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `TestLocalFileSystemClient::test_write_text_read_text_roundtrip`
- `TestLocalFileSystemClient::test_utf8_preserved` (chars: `àèìòù`)
- `TestLocalFileSystemClient::test_write_bytes_read_bytes_roundtrip`
- `TestLocalFileSystemClient::test_write_stream_read_stream_roundtrip`
- `TestLocalFileSystemClient::test_write_creates_missing_parent_dirs`
- `TestLocalFileSystemClient::test_overwrite_existing_file`
- `TestLocalFileSystemClient::test_exists_returns_none_for_existing_file`
- `TestLocalFileSystemClient::test_exists_raises_file_not_found_for_missing_file`
- `TestLocalFileSystemClient::test_exists_raises_permission_error_on_traversal_before_not_found`

### 5. Implement `AsyncLocalFileSystemClient` (async)

Create `src/commons/clients/file_system/async_local_file_system_client.py`:

```python
class AsyncLocalFileSystemClient(BaseFileSystemClient, AsyncFileReaderInterface, AsyncFileWriterInterface):
    ...
```

All seven methods implemented with `aiofiles.open`.
`write_stream` consumes `AsyncIterable[bytes]` with `async for`.
`async exists(path)` → delegates to `_get_safe_read_path(path)` (sync, no await). Raises `PermissionError` on traversal (precedence), `FileNotFoundError` if missing, returns `None` on success.
Same logging and error-handling pattern as the sync client.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `TestAsyncLocalFileSystemClient::test_write_text_read_text_roundtrip`
- `TestAsyncLocalFileSystemClient::test_utf8_preserved`
- `TestAsyncLocalFileSystemClient::test_write_bytes_read_bytes_roundtrip`
- `TestAsyncLocalFileSystemClient::test_write_stream_read_stream_roundtrip`
- `TestAsyncLocalFileSystemClient::test_write_creates_missing_parent_dirs`
- `TestAsyncLocalFileSystemClient::test_exists_returns_none_for_existing_file`
- `TestAsyncLocalFileSystemClient::test_exists_raises_file_not_found_for_missing_file`

### 6. Wire up `__init__.py` files and update `clients/__init__.py`

`src/commons/clients/file_system/__init__.py` re-exports:
`BaseFileSystemClient`, `FileReaderInterface`, `FileWriterInterface`,
`AsyncFileReaderInterface`, `AsyncFileWriterInterface`,
`LocalFileSystemClient`, `AsyncLocalFileSystemClient`.

Update `src/commons/clients/__init__.py` to include all seven names.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Import smoke test: `from commons.clients.file_system import LocalFileSystemClient` (covered by DoD)

## Definition of Done

Variable block (plan-specific):

- [ ] `grep -r "LocalFileSystemClient\|AsyncLocalFileSystemClient\|FileReaderInterface\|FileWriterInterface\|AsyncFileReaderInterface\|AsyncFileWriterInterface\|BaseFileSystemClient" src/commons/clients/__init__.py` — all seven names present
- [ ] `python -c "from commons.clients.file_system import LocalFileSystemClient, AsyncLocalFileSystemClient, FileReaderInterface, FileWriterInterface, AsyncFileReaderInterface, AsyncFileWriterInterface, BaseFileSystemClient; print('OK')"` exits 0
- [ ] `grep "logging.getLogger" src/commons/clients/file_system/local_file_system_client.py src/commons/clients/file_system/async_local_file_system_client.py` — logger present in both concrete classes
- [ ] `grep "Path traversal attempt detected" src/commons/clients/file_system/_base_file_system_client.py` — security message present
- [ ] `uv run pytest tests/commons/clients/test_file_system_client.py` green (no integration marker needed — all unit tests)

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Agent `doc-architect` invoked (if available)
- [ ] Plan updated to `status: Implemented`
