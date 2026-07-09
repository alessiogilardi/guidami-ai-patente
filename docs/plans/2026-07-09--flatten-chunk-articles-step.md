---
status: Implemented
effort: M
---
# Flatten Chunk Articles Step

References:

## Context and motivation

ChunkArticlesStep takes a 'source' constructor arg used only to print it in a log message; the actual chunking logic already delegates to ArticleChunker, which has its own independently injected 'source'. The whole step class exists just to wrap a flat-map (list[Article] -> list[list[Chunk]] -> list[Chunk]), duplicating the generic ApplyStep + ForEach(...) pattern already used elsewhere in knowledge_flows.py (e.g. clean_articles, enrich steps). No generic list[list[T]] -> list[T] flatten transform exists yet in commons/use_cases (only FlattenQuiz, which is quiz-domain-specific and also does mapping, not pure flatten).

### Affected areas

New: `commons/use_cases/flat_map.py` (generic `FlatMap[T, U]` combinator, `list[T] -> list[U]` via a per-element `Callable[[T], Iterable[U]]`) + export in `commons/use_cases/__init__.py`. Removed: `orchestrators/steps/knowledge/chunk_articles_step.py` + its export in `steps/knowledge/__init__.py`. Modified: `orchestrators/knowledge_flows.py` (`chunk_step` becomes `ApplyStep("chunk_articles", FlatMap(article_chunker), ...)`); `services/quiz/flatten_quiz.py` (prominent TODO annotating it as a follow-up consumer of `FlatMap`, no behaviour change). Tests: remove `test_chunk_articles_step.py`, add `tests/commons/use_cases/test_flat_map.py`, verify `test_knowledge_flows.py` still passes unchanged. Docs: `docs/architecture.md` references `chunk_articles`/`ChunkArticlesStep` and needs updating (Second Brain, after implementation). Out of scope for this plan: `flowstep/steps/apply_step.py` — the generic count-log enrichment that recovers the lost per-stage observability is owned by the user and applied externally (see Decisions).

### Success criteria

`ChunkArticlesStep` class and its test file no longer exist; the `chunk_articles` flow step is built via `ApplyStep` + `FlatMap(article_chunker)` in `knowledge_flows.py`; a generic reusable `FlatMap` use case exists in `commons/use_cases` (accepting `Callable[[T], Iterable[U]]`) with its own tests; `FlattenQuiz` carries a prominent TODO flagging it as a future `FlatMap` consumer; all existing tests pass; `docs/architecture.md` no longer references `ChunkArticlesStep`.

## Non-goals

Do not change `ArticleChunker` (including its own injected `source`, needed for chunking). Do not touch `FlattenQuiz` or the quiz flow. No behavior change: same chunk order, same chunks produced, repealed still included unfiltered.

## Decisions

- **`FlatMap` combinator instead of separate `ForEach` + `Flatten` primitives.** During design, the brainstormed idea of a bare `Flatten` (`list[list[T]] -> list[T]`) was replaced with a single `FlatMap[T, U]` use case that combines map + concat (`Callable[[T], list[U]]` applied per element, results concatenated). Rationale: the actual recurring need in this codebase is "one input produces N outputs, concatenated" (e.g. one article -> N chunks), which is exactly the `flatMap`/`concatMap` idiom from functional collections — naming it directly communicates intent at the call site (`FlatMap(article_chunker)`) instead of requiring the reader to recognize that two chained transforms (`ForEach(...)`, `Flatten()`) compose into a flat-map. `Flatten` alone would only be useful once data is already nested, which is not this project's actual use case. User-confirmed during the design phase.
- **No changes to `ArticleChunker`'s public shape.** It stays `UseCase[EnrichedArticleModel, list[EmbeddableChunkModel]]`, usable standalone by `FlatMap` without modification.
- **Per-source count log is recovered externally, not in this plan.** `ChunkArticlesStep` logged `"Chunked N articles for source 'X' -> M chunks"`. The right fix for the lost per-stage input/output counts (genuine ingestion observability: "expected ~1300 chunks, got 1289?") is to enrich `ApplyStep`'s generic log with input/output list lengths, recovering the observability for **every** `ApplyStep`-based step, not just chunk. That change lives in `flowstep/steps/apply_step.py`, which is the generic domain-agnostic framework; the user owns `flowstep/` and applies this enhancement **externally**, so it is deliberately out of scope for this plan. No domain-specific count log is reintroduced here.
- **`FlatMap.fn` typed `Callable[[T], Iterable[U]]`, not `Callable[[T], list[U]]`.** `list` is invariant under pyright: a mapper returning a generator, `tuple`, or `Sequence[U]` would be a type error despite being valid for the concatenation. Accepting `Iterable[U]` in and producing `list[U]` out keeps `FlatMap` permissive like `ForEach` (which accepts "any callable"), while `ArticleChunker` (returning `list[EmbeddableChunkModel]`) stays compatible.
- **`FlattenQuiz` consolidation is a flagged follow-up, not in scope.** `FlattenQuiz` (`services/quiz/flatten_quiz.py`) is conceptually a flat-map — for each parent question it produces N `CleanedQuizModel`, with the per-element `fn` closing over the parent — so it is a latent second consumer of `FlatMap`. Collapsing it is deliberately out of scope here (see Non-goals) to keep the quiz flow untouched, but the target class is annotated in-code with a prominent TODO so the consolidation is not lost. This also validates that `FlatMap` is general enough to express more than the chunking use case.

## Open questions / Risks

The one risk identified — losing the per-source chunk-count log line — is addressed **outside** this plan: the generic count-log enrichment to `ApplyStep` is applied externally by the user (see Decisions), so this plan proceeds without reintroducing any domain-specific log and without touching `flowstep/`. Note the `EMBEDDABLE_CHUNKS` benign WARNING referenced in `build_knowledge_indexing_flow`'s docstring: it stays valid (the `ApplyStep(chunk_articles)` still produces the key that `EmbedChunksStep` re-declares), but the docstring's textual reference to `ChunkArticlesStep` must be reworded — the DoD `grep` over `src` catches it.

## Implementation tasks
### 1. Add the generic `FlatMap` use case

Create `commons/use_cases/flat_map.py` with `FlatMap[T, U](UseCase[list[T], list[U]])`, constructor takes `fn: Callable[[T], Iterable[U]]` (see Decisions — `Iterable`, not `list`, for variance), `execute` maps `fn` over each element of the input list and concatenates the results into a `list[U]` (order preserved). Mirror `for_each.py`'s file layout, docstring style (Google style, Args sections), and generic-type conventions. Export `FlatMap` from `commons/use_cases/__init__.py` (`from .flat_map import FlatMap as FlatMap`).

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `tests/commons/use_cases/test_flat_map.py`: concatenates results from multiple elements in order; empty input list -> empty output; an element whose `fn` call returns an empty list contributes nothing; `fn` returning a non-`list` `Iterable` (e.g. a generator) still concatenates correctly; delegates to `fn` via `__call__` for each element (mock-based, asserting call count and args, mirroring `ForEach`'s existing test style).

### 2. Replace `ChunkArticlesStep` with `ApplyStep` + `FlatMap` in the indexing flow

In `orchestrators/knowledge_flows.py`, replace the `chunk_step = ChunkArticlesStep(...)` construction with:
```
chunk_step = ApplyStep(
    "chunk_articles",
    FlatMap(ArticleChunker(typed_source)),
    input_key=context_keys.ENRICHED_ARTICLES,
    output_key=context_keys.EMBEDDABLE_CHUNKS,
)
```
Update imports (`FlatMap` from `commons.use_cases`, drop `ChunkArticlesStep`). Update the function's docstring "Mappatura step" line to reflect the new step composition. Delete `orchestrators/steps/knowledge/chunk_articles_step.py` and its export in `orchestrators/steps/knowledge/__init__.py`. Delete `tests/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/test_chunk_articles_step.py`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py` requires no changes — it asserts through `build_knowledge_indexing_flow`'s public behavior (flow instance, name, required keys, validation, and the two `@pytest.mark.integration` end-to-end tests), none of which reference `ChunkArticlesStep` directly. Run the existing suite (excluding `integration`) to confirm no regression.

### 3. Annotate `FlattenQuiz` as a follow-up `FlatMap` consumer

In `services/quiz/flatten_quiz.py`, add a prominent module- or class-level `TODO` (Google-style, English) stating that `FlattenQuiz` is a latent `FlatMap[ParsedQuizModel, CleanedQuizModel]` consumer — the per-parent `fn` produces N `CleanedQuizModel` closing over the parent — and can be collapsed onto the generic `FlatMap` once the quiz flow is in scope. No behaviour change, no import of `FlatMap` yet (avoids an unused import); this is a signpost only.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- N/A (comment-only change); verified via the DoD `grep` for the TODO marker.

### 4. Update Second Brain docs

Run the `second-brain:update` skill to bring `docs/architecture.md` in line with the removal of `ChunkArticlesStep` and the introduction of the `FlatMap` pattern for one-to-many transforms.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- N/A (documentation-only step); verified via `grep -r "ChunkArticlesStep" docs/` returning no matches.

## Definition of Done

Variable block (plan-specific):

- [x] `python -c "from commons.use_cases import FlatMap"` succeeds
- [x] `grep -n "Iterable" src/commons/use_cases/flat_map.py` shows the `fn` parameter typed `Callable[[T], Iterable[U]]`
- [x] `grep -r "ChunkArticlesStep" src tests` returns no matches
- [x] `grep -r "ChunkArticlesStep" docs` returns no matches
- [x] `grep -ni "TODO.*FlatMap" src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py` returns the follow-up marker
- [x] `uv run pytest tests/commons/use_cases/test_flat_map.py -v` all pass
- [x] `uv run pytest tests/guidami_ai_patente_ingestor/orchestrators/test_knowledge_flows.py -v` all pass (non-integration)

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests)
- [x] `uv run pyright` clean
- [x] `uv run ruff check src tests` clean
- [x] Plan updated to `status: Implemented`
