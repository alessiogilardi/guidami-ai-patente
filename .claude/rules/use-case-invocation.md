# `UseCase`/`AsyncUseCase` — when to use one, and how to invoke it

## When a class should be a `UseCase`/`AsyncUseCase`

The deciding question is the shape of the **public contract**, not the internal
complexity: does the class reduce to one well-defined input and one well-defined
output? If yes, it is a `UseCase[T_In, T_Out]`/`AsyncUseCase[T_In, T_Out]],
regardless of how many repositories, services, clients, or config objects it
depends on to get there, and regardless of how much internal orchestration
(concurrency, retries, multi-step sequencing) it takes to produce that output.
Dependency count and internal complexity are not disqualifying — they are exactly
what `UseCase` is for: hiding an arbitrarily complex transformation behind a
single typed `execute(request) -> result`.

What *does* disqualify a class:
- **More than one distinct public operation** (e.g. a class exposing `propose`,
  `fetch` and `topics`, each with its own input/output shape) — `UseCase` has
  exactly one `execute` method; a multi-operation class would have to be split
  into one `UseCase` per operation, which is only worth it if those operations
  don't share a natural home as one cohesive service.
- **No meaningful output** — a void, side-effecting diagnostic or startup check
  has nothing for `T_Out` to type; forcing `UseCase[T_In, None]` on it adds
  ceremony without the benefit (a real return value to compose on).

`UseCase` and a class's *placement* (`services/`, `orchestrators/`, ...) are
independent axes: a complex async pipeline with retries and concurrency control
can live in `orchestrators/` as a `*Pipeline` *and* implement `AsyncUseCase` at
the same time, if its own public contract is one input → one output — the two
conventions answer different questions ("where does this file live" vs. "what
is its calling contract") and are not mutually exclusive.

## Invocation — always via `__call__`, never `.execute()`

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
`src/guidami_ai_patente_ingestor/`, plus — since spec 0013 — six specific classes:
`src/guidami_ai_patente/services/`'s `ExplanationStatusService`, `QuizImageService`,
`QuizAnswerChecker`, and `src/labeling/services/`'s `CandidateSetService`,
`QuestionLexemeService`, `GoldenSetLabelingService`. This is not a blanket extension
to every class in those two directories — `QuizProposalService`, `HealthCheckService`
and `JudgeCoherenceChecker` in `guidami_ai_patente/services/` stay outside `UseCase`
(multi-operation or void-output; see each class's own docstring). A repo-wide sweep of
pre-existing `.execute()` call sites outside `commons/ai/embedding/` is tracked
separately — new code and any file touched for another reason should follow this rule
going forward.
