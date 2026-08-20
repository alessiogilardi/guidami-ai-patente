# Code Conventions

Project-specific conventions. General Python rules (typing, PEP 8 style, relative/absolute
imports, SOLID, configuration patterns) live in `~/.claude/rules/python/`.

## Loop bodies — no `continue`, guard with a nested `if` instead

Do not use `continue` to skip an iteration. Wrap the rest of the loop body in a
positive `if` condition instead.

```python
# WRONG
for quiz in questions:
    if quiz.text in seen_texts:
        continue
    contexts[quiz.topic].append(quiz.text)
    seen_texts.add(quiz.text)

# RIGHT
for quiz in questions:
    if quiz.text not in seen_texts:
        contexts[quiz.topic].append(quiz.text)
        seen_texts.add(quiz.text)
```

User preference, no further rationale given — apply uniformly across `src/` and
`tests/`. This does not affect the separate, already-established preference for
early *returns* in functions (`~/.claude/rules/python/standards.md`); it is
specifically about `continue` inside loops.

## Language — English only

Docstrings, inline comments, log messages, and print/console output are always written
in English, regardless of the language used in the conversation with the user or in
commit messages. This applies uniformly across `src/` and `tests/`.

Domain proper nouns that are legitimately Italian (e.g. "Codice della Strada", "CdS",
"CAP") are not translated. Quiz/legal-text content stored as data (fixtures, DB rows)
is not documentation and is unaffected by this rule.

### Exception — prompt-facing text on agent response DTOs

A response model's class docstring and `Field(description=...)` under
`agents/dto/*/*_response.py` are shipped to the LLM by pydantic-ai
(`Agent(output_type=...)` in `BaseAgent` sends the model's JSON schema — docstring
becomes the output/tool description, `Field(description=...)` becomes the field
schema). They are functionally *prompt content*, not code documentation: write
them in Italian. The domain is Italian legal text (CdS/CAP) and the system
prompts are already Italian, so Italian descriptions improve extraction fidelity
and avoid an IT/EN split within the same LLM call.

This exception applies to **every** agent response DTO (class docstring + field
descriptions), for cross-agent consistency. It does **not** apply to request DTOs
(`*_request.py`): their values are substituted into the user-prompt template, but
their docstrings/descriptions are never shipped to the model as schema, so they
stay English. Every other docstring/comment/log on a response DTO (e.g. an inline
note explaining this exception) stays English — only the LLM-facing docstring and
`Field(description=...)` text switch to Italian.

## Pydantic

Configuration classes (any file under `configs/`) must set
`model_config = ConfigDict(frozen=True)`.

## Enums — their own `enums/` package, never `models/`

An enumeration is a closed vocabulary, not a data carrier. It goes in an `enums/` package
alongside `entities/` and `models/` — **not** inside `models/`, which is reserved for DTOs,
Pydantic models and value objects that *hold* data.

```
src/domain/
├── entities/   # insertable projections of DB rows
├── enums/      # closed vocabularies (StrEnum, IntEnum, Enum)
└── models/     # DTOs, Pydantic models, value objects
```

One enum per file, named after the enum in snake_case (`lexeme_field.py` →
`LexemeField`), re-exported from the package `__init__.py` like every other package.

Placement follows the same test as entities: an enum that names part of a **shared shape**
(a DB column's legal values, a field vocabulary another module will also need) belongs in
`src/domain/enums/`. An enum that is genuinely internal to one module — never referenced
outside it — may live in that module's own `enums/` package instead, per the
self-containment rule in `cli-structure.md`.

Prefer `StrEnum` (Python 3.12+) when the members' values are strings that cross a boundary
(config, DB, JSON): members compare equal to their string value, so serialization and
`getattr`/dict lookups work without `.value` gymnastics — while `pyright` still rejects a
bare string at the call site, which is the whole point of using an enum over `str`.

### Values come from `auto()`, not hand-written literals

```python
# WRONG — the member name and its value are the same word, written twice
class LexemeField(StrEnum):
    TOPIC = "topic"
    IMAGE_DESCRIPTION = "image_description"

# RIGHT — auto() derives the value from the name
class LexemeField(StrEnum):
    TOPIC = auto()
    IMAGE_DESCRIPTION = auto()
```

`StrEnum._generate_next_value_` returns `name.lower()`, so `IMAGE_DESCRIPTION = auto()`
carries the value `"image_description"`. On a plain `Enum`/`IntEnum`, `auto()` yields
successive integers starting at 1. Either way the value stops being a second place to edit,
and a member rename can no longer leave a stale literal behind.

**The one exception**: an enum whose values are an *external contract* that must survive a
member rename — a value already persisted in a DB column, written into a file format, or
sent over an API. There the value is data, not a restatement of the name, so it is written
explicitly and an inline comment says why. This is a narrow exception: a value that merely
*happens* to be consumed elsewhere but is free to change with the name is not one.

## Data structures — `BaseModel` or `dataclass` by default

Structured data uses **only** Pydantic `BaseModel` or a stdlib `dataclass`. `NamedTuple` and
`TypedDict` are allowed **only** with a clear, stated reason — never as a default choice.

Reasons that can qualify (non-exhaustive):
- The structure holds **callables** as fields — a `BaseModel` can't type a `Callable` field
  cleanly without `arbitrary_types_allowed=True`, which defeats the point of using Pydantic;
  a `dataclass` would also work, but `NamedTuple`'s default immutability fits a static,
  never-mutated registry entry better.
- Positional unpacking is actually used at the call site.
- Interop with an API that specifically expects a plain tuple or dict (e.g. a stdlib/
  third-party signature).

Whichever reason applies must be stated **in the class docstring or an inline comment** —
the choice has to be visible to a reader without having to ask why.

## Entities — insertable projection of the table row

An entity in `src/domain/entities/` models the **insertable projection** of its DB row,
not the full row:

- **Class name suffixed `Entity`** (e.g. `ArticleEntity`, `ArticleCommaEntity`,
  `QuizQuestionEntity`, `LlmCallLogEntity`) — disambiguates the persisted-row type
  from same-concept models elsewhere in the pipeline (e.g. `CleanedArticleModel`,
  `EmbeddableArticleComma`) at the call site, without relying on the import path
  alone. Applies uniformly to every class under `domain/entities/`, regardless of
  package (`knowledge/`, `quiz/`, `observability/`).
- 1:1 with the table's **writable** columns.
- **DB-generated columns are omitted** (`id BIGSERIAL`, `created_at DEFAULT now()`) —
  never declared as `Optional` fields "populated only on read". An always-`None` field on
  the write path lies about its type and forces pointless None-checks downstream.
- Data needed in the pipeline but not persisted lives on an intermediate model
  (`models/…`) plus a mapper — never on the entity.
- If a future read path needs row identity, prefer the natural keys already in the schema
  (e.g. `quiz_questions.number` UNIQUE) or introduce a separate read model with a
  non-nullable `id` — do not weaken the write entity.

These are persistence DTOs by design. Rich domain entities (behavior + invariants) are
deferred until the FastAPI app introduces real domain logic, and will be added pull-based
where an invariant actually emerges.

## Services — class naming in `services/` folders

A class placed in any `services/` folder (top-level or nested, e.g. `cli/services/evaluation/`)
that is genuinely a service — domain logic with injected config/dependencies, not a stateless
data container — is named with a suffix that says what it specifically does.

- **A more specific, already-established role suffix always wins**: `*Calculator`
  (single-purpose computation, e.g. `AdherenceCalculator`, `RankingCalculator`), `*Writer`
  (persists/renders output, e.g. `EvaluationArtifactWriter`), `*Evaluator`
  (`RetrievalEvaluator`), `*Inspector` (`StatusInspector`), `*Checker` (`TableHealthChecker`),
  or a port-implementation class named after the port it implements (`*Tracker` for
  `LlmCallTracker`, `*Reporter` for `ProgressReporter` — `NullProgressReporter`,
  `QueuedLlmCallTracker`).
- **`*Service` is the default fallback** — use it only when no more specific role name applies
  (e.g. `EmbeddingService`, `RetrievalJudgeEvaluationService`). Never leave a genuine service
  class with a bare, unsuffixed name.
- **`UseCase`/`AsyncUseCase` subclasses placed under a `services/` folder also take the
  `Service` suffix**, appended after their action-verb name (e.g. `ArticleCleaner` →
  `ArticleCleanerService`, `ImageDescriptionEnricher` → `ImageDescriptionEnricherService`).
  This overrides the general `feedback_usecase_naming` rule (no `Service`/`UseCase` suffix)
  specifically for this location: the folder is the naming signal, so a class living under
  `services/` must read as a service by name alone, regardless of its base class.

**Does not apply to:**
- `Protocol` classes (ports/interfaces) and private (`_`-prefixed) helper classes.
- Plain data containers (`NamedTuple`, dataclasses with no injected dependency) — not services.

## PostgresClient — vector cast

`PostgresClient` requires the explicit cast `%s::vector` for vector parameters:
psycopg adapts `list[float]` to the Postgres `array` type, which is incompatible with
the pgvector `<=>` operator.

```python
# WRONG
cursor.execute("SELECT ... WHERE embedding <=> %s", [vector])

# RIGHT
cursor.execute("SELECT ... WHERE embedding <=> %s::vector", [vector])
```

## Collection transformations — direct iteration over index-tracking

Do **not** build a side list of `(index, payload)` tuples and then splice results back
by position. When a producer guarantees its output is aligned 1:1 to its input (e.g.
`EmbeddingService.execute` returns vectors in input order), exploit that invariant
instead of re-deriving alignment through positional indices:

- filter the input,
- call the producer,
- consume the results in lockstep (`iter()` + `next()`, or `zip(..., strict=True)`),
- rebuild in a single pass.

Throwaway destructuring is the smell that flags this anti-pattern — if you write
`for (i, _), x in zip(...)` or `[y for _, y in pairs]`, you are carrying state you
do not need.

```python
# WRONG — track indices, splice back by position
to_embed = [(i, item.meta) for i, item in enumerate(items) if item.meta is not None]
vectors = service.execute([meta for _, meta in to_embed])
result = list(items)
for (i, _), vector in zip(to_embed, vectors, strict=True):
    result[i] = result[i].model_copy(update={"embedding": vector})

# RIGHT — lockstep consumption, one rebuild pass, no indices
to_embed = [item for item in items if item.meta is not None]
vectors = service.execute(to_embed)
vectors_iter = iter(vectors)
result = [
    item.model_copy(update={"embedding": next(vectors_iter)}) if item.meta is not None else item
    for item in items
]
```

Rationale: KISS — the indices are accidental complexity the ordering guarantee makes
superfluous. This class of defect is **not** caught by a linter (no tool knows the
producer preserves order); enforcement is this rule plus `/code-review` / `/simplify`.
`ruff` `SIM` and `C901` (mccabe, `max-complexity = 10`) are enabled as a mechanical
floor for the correlated smells, not as a substitute for review.

## Shape-polymorphic APIs — one method per shape, never a `T | Sequence[T]` union

A method must not accept or return `T | Sequence[T]`. Split it into one method per
shape, each validating what it actually got.

```python
# WRONG — union forces every caller to cast, and the writer to sniff the shape
def load(self, file_name: str | Path) -> T | Sequence[T]: ...
def write(self, data: T | Sequence[T], file_name: str | Path) -> None: ...

# RIGHT — monomorphic, self-describing, each rejects the wrong shape explicitly
def load_one(self, file_name: str | Path) -> T: ...
def load_list(self, file_name: str | Path) -> list[T]: ...
def write_one(self, item: T, file_name: str | Path) -> None: ...
def write_list(self, items: Sequence[T], file_name: str | Path) -> None: ...
```

Rationale: the caller always knows the shape statically, so the union adds no
flexibility — it only forces an unchecked `cast()` at every call site (a cast that
silently lies if the file's actual shape differs) and pushes the writer into runtime
type-sniffing like `isinstance(data, Sequence) and not isinstance(data, (str, bytes,
dict))`, whose blacklist breaks for any `T` that happens to implement `Sequence`.
Splitting turns both into a real, message-carrying `ValueError`.

**Name overloaded methods after the source, not the cardinality.** `load_list` (one
file holding an array) and `load_dir` (a directory, one object per file) both return
`list[T]`; a name like `load_all` does not say which one it is. See
`BaseFileRepository` / the `FileRepository` protocol in
`src/commons/repositories/file_repository/` for the reference implementation.

## Tests — no `__init__.py` in test directories

Test directories never contain `__init__.py`. Any test directory named after a source
package (e.g. `tests/domain/`) would create a namespace collision with `src/<package>/`
in `sys.path`, causing imports inside tests to resolve to the empty test package instead
of the real source package. The rule applies uniformly to all directories under `tests/`.

## Tests — integration marker

`@pytest.mark.integration` marks tests that require external services (Postgres,
model downloads). `uv run pytest` without flags skips them automatically.
