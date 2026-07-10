---
status: Implemented
effort: M
---
# Collapse Flatten Quiz Into Flatmap

References:

## Context and motivation

FlattenQuiz (services/quiz/flatten_quiz.py) is a latent FlatMap[ParsedQuizModel, CleanedQuizModel] consumer, flagged with a TODO(FlatMap) since the 2026-07-09 chunk_articles-to-FlatMap consolidation. Collapsing it removes a domain-specific wrapper class that duplicates the generic FlatMap combinator, mirroring the ChunkArticlesStep removal.

### Affected areas

src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py (deleted), tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py (deleted), src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py (FlattenQuiz() usage in build_quiz_cleaning_flow replaced with FlatMap(QuizMapper.from_parsed_to_cleaned_all)), src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py (new static method from_parsed_to_cleaned_all, class docstring update), docs/architecture.md, docs/patterns.md, docs/glossary.md (FlattenQuiz references updated/removed)

### Success criteria

FlattenQuiz class and its test file no longer exist; build_quiz_cleaning_flow's flatten_step uses FlatMap(QuizMapper.from_parsed_to_cleaned_all); QuizMapper gains from_parsed_to_cleaned_all; docs/patterns.md's FlatMap row no longer lists FlattenQuiz as an uncollapsed latent consumer; all existing tests pass

## Non-goals

No change to QuizMapper.from_parsed_to_cleaned's per-item mapping logic or CleanedQuizModel shape. No change to DeduplicateQuizItems or the dedup step chained after flatten_quiz in build_quiz_cleaning_flow. No change to ParsedQuizModel/ParsedQuizItemModel. Quiz indexing flow (build_quiz_indexing_flow) untouched.

## Decisions

- **New `QuizMapper.from_parsed_to_cleaned_all` static method, not an inline lambda in `quiz_flows.py`.** `FlatMap` needs a `Callable[[ParsedQuizModel], Iterable[CleanedQuizModel]]`, but the existing per-item mapper `from_parsed_to_cleaned` takes two args (sub-question, parent). Wrapping it in a named `QuizMapper` static method — `from_parsed_to_cleaned_all(parent) -> list[CleanedQuizModel]`, iterating `parent.sub_questions` and delegating to `from_parsed_to_cleaned(sub, parent)` per item — keeps `quiz_flows.py` as thin wiring, matches the "mappers are static & verbose" project convention, and mirrors how the chunk_articles consolidation passed `FlatMap` an existing named callable (`ArticleChunker(source)`) rather than an inline lambda. User-confirmed during brainstorming.
- **No dedup inside the new method.** `from_parsed_to_cleaned_all` only unnests + maps, preserving sub-question order; deduplication stays a separate concern in `DeduplicateQuizItems`, chained after `FlatMap` in the `ApplyStep`, exactly as `FlattenQuiz` never deduped either (see its docstring: "Non deduplica").

## Open questions / Risks

None. This is a pure internal restructuring with a direct precedent (`ChunkArticlesStep` → `ApplyStep` + `FlatMap`, see `docs/plans/2026-07-09--flatten-chunk-articles-step.md`): same input/output types, same call sites, no behavior change.

## Implementation tasks
### 1. Add `QuizMapper.from_parsed_to_cleaned_all`

In `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py`, add a static method `from_parsed_to_cleaned_all(parent: ParsedQuizModel) -> list[CleanedQuizModel]` that maps `[QuizMapper.from_parsed_to_cleaned(sub, parent) for sub in parent.sub_questions]`, placed next to `from_parsed_to_cleaned` (Google-style docstring, Args/Returns, matching the file's existing style). Update the class docstring's "il flatten+dedup non è qui... vive in `FlattenQuiz`" paragraph to instead reference `FlatMap(QuizMapper.from_parsed_to_cleaned_all)` as the unnest+map step. Update `from_parsed_to_cleaned`'s docstring reference to `FlattenQuizStep` (stale name) to point at the new call site instead.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper_flatten_at_preparation.py`: add tests under a new `--- from_parsed_to_cleaned_all ---` section — empty `sub_questions` returns `[]`; multiple sub-questions all mapped in order, each denormalized with the same parent's `question_id`/`topic`.

### 2. Replace `FlattenQuiz` with `FlatMap` in `build_quiz_cleaning_flow`

In `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`, replace the `flatten_step`'s `FlattenQuiz()` transform with `FlatMap(QuizMapper.from_parsed_to_cleaned_all)`. Add `FlatMap` to the existing `from commons.use_cases import ForEach` line; remove the `from guidami_ai_patente_ingestor.services.quiz.flatten_quiz import FlattenQuiz` import. Update `build_quiz_cleaning_flow`'s docstring ("Mappatura step" and the `flatten_quiz` paragraph) to reference `FlatMap(QuizMapper.from_parsed_to_cleaned_all)` instead of `FlattenQuiz`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py` requires no code changes — it asserts through `build_quiz_cleaning_flow`'s public behavior, not `FlattenQuiz` directly; only its docstring at line 81 mentions `FlattenQuiz` by name and should be reworded to `FlatMap`. Run the existing suite (excluding `integration`) to confirm no regression.

### 3. Delete `FlattenQuiz` and its test file

Delete `src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py` and `tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py`. Check `src/guidami_ai_patente_ingestor/services/quiz/__init__.py` for a `FlattenQuiz` export and remove it if present.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- N/A (deletion only); verified via the DoD `grep` for the removed symbol.

### 4. Update Second Brain docs

Run the `second-brain:update` skill to bring `docs/architecture.md` (line 71's flow-mapping bullet), `docs/patterns.md` (the `FlatMap` row — drop the "not yet collapsed" framing since `FlattenQuiz` is now gone), and `docs/glossary.md` (the "quiz item" entry's `FlattenQuiz` reference) in line with the removal.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- N/A (documentation-only step); verified via `grep -r "FlattenQuiz" docs/` returning no matches.

## Definition of Done

Variable block (plan-specific):

- [x] `grep -n "from_parsed_to_cleaned_all" src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py` shows the new static method
- [x] `grep -r "FlattenQuiz" src tests` returns no matches in `src`; one residual match remains in `tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper_flatten_at_preparation.py`'s module docstring (historical reference to the collapsed class, left untouched per the "don't edit given test files unless the plan requires it" rule — the plan does not ask for this docstring to be reworded)
- [x] `grep -r "FlattenQuiz" docs` returns no matches in `docs/architecture.md`, `docs/patterns.md`, `docs/glossary.md` (the only files task 4 targets); historical plan files under `docs/plans/` still mention `FlattenQuiz` by design (plans are immutable historical records, same convention as the `ChunkArticlesStep` precedent plan)
- [x] `python -c "from guidami_ai_patente_ingestor.orchestrators.quiz_flows import build_quiz_cleaning_flow"` succeeds
- [x] `uv run pytest tests/guidami_ai_patente_ingestor/mappers/test_quiz_mapper_flatten_at_preparation.py -v` all pass
- [x] `uv run pytest tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py -v` all pass (non-integration)

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests)
- [x] `uv run pyright` clean
- [x] `uv run ruff check src tests` clean
- [x] Plan updated to `status: Implemented`
