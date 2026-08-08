# Invoking a `UseCase`/`AsyncUseCase` — always via `__call__`, never `.execute()`

`UseCase.__call__`/`AsyncUseCase.__call__` (`commons/use_cases/use_case.py`) are
`@final` and delegate to `execute` precisely to be the public invocation point;
`execute` is the abstract method to *implement*, not to call from the outside.

Every consumer of a `UseCase`/`AsyncUseCase` instance invokes it via `__call__`,
never via `.execute()` directly:

```python
# WRONG — bypasses the public invocation point
vectors = self._embedding_service.execute(texts)

# RIGHT — invokes via __call__
vectors = self._embedding_service(texts)
```

`ForEach`'s docstring (`fn: Callable applied to each element; accepts UseCase
instances (invoked via __call__)`) already presupposed this convention; this
rule makes it explicit and applies it uniformly.

## Scope

Applies to every `UseCase`/`AsyncUseCase` consumer in `src/commons/` and
`src/guidami_ai_patente_ingestor/`. A repo-wide sweep of pre-existing
`.execute()` call sites outside `commons/ai/embedding/` is tracked separately —
new code and any file touched for another reason should follow this rule going
forward.
