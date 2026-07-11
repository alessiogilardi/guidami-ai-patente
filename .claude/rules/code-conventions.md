# Code Conventions

Project-specific conventions. General Python rules (typing, PEP 8 style, relative/absolute
imports, SOLID, configuration patterns) live in `~/.claude/rules/python/`.

## Language — English only

Docstrings, inline comments, log messages, and print/console output are always written
in English, regardless of the language used in the conversation with the user or in
commit messages. This applies uniformly across `src/` and `tests/`.

Domain proper nouns that are legitimately Italian (e.g. "Codice della Strada", "CdS",
"CAP") are not translated. Quiz/legal-text content stored as data (fixtures, DB rows)
is not documentation and is unaffected by this rule.

## Pydantic

Configuration classes (any file under `configs/`) must set
`model_config = ConfigDict(frozen=True)`.

## Entities — insertable projection of the table row

An entity in `src/domain/entities/` models the **insertable projection** of its DB row,
not the full row:

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

## Tests — no `__init__.py` in test directories

Test directories never contain `__init__.py`. Any test directory named after a source
package (e.g. `tests/domain/`) would create a namespace collision with `src/<package>/`
in `sys.path`, causing imports inside tests to resolve to the empty test package instead
of the real source package. The rule applies uniformly to all directories under `tests/`.

## Tests — integration marker

`@pytest.mark.integration` marks tests that require external services (Postgres,
model downloads). `uv run pytest` without flags skips them automatically.
