# Code Conventions

Project-specific conventions. General Python rules (typing, PEP 8 style, relative/absolute
imports, SOLID, configuration patterns) live in `~/.claude/rules/python/`.

## Pydantic

Configuration classes (any file under `configs/`) must set
`model_config = ConfigDict(frozen=True)`.

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

## Tests — no `__init__.py` in test directories

Test directories never contain `__init__.py`. Any test directory named after a source
package (e.g. `tests/domain/`) would create a namespace collision with `src/<package>/`
in `sys.path`, causing imports inside tests to resolve to the empty test package instead
of the real source package. The rule applies uniformly to all directories under `tests/`.

## Tests — integration marker

`@pytest.mark.integration` marks tests that require external services (Postgres,
model downloads). `uv run pytest` without flags skips them automatically.
