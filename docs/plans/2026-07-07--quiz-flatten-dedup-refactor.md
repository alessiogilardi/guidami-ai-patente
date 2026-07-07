---
status: Implemented
effort: M
---
# Quiz Flatten Dedup Refactor

References: [_index.md](_index.md),
[docs/architecture/modules/ingestor/quiz_pipelines.md](../architecture/modules/ingestor/quiz_pipelines.md)
(documents the decision this plan supersedes),
[docs/architecture/patterns.md](../architecture/patterns.md) (`ApplyStep` composition pattern).

## Context and motivation

FlattenQuiz (services/quiz/flatten_quiz.py) is a monolithic UseCase that unnests, deduplicates, and maps parsed quiz items in one opaque execute() method, used as a single black-box ApplyStep in build_quiz_cleaning_flow. Separately, build_quiz_indexing_flow deduplicates EnrichedQuizModel via a private free function (_dedup_enriched_quiz) with the exact same key logic (normalized text, correct_answer, image) duplicated in two places. Refactor both flows to compose small, named ApplyStep transforms (mirroring the existing indexing flow's dedup+ForEach(mapper) chaining pattern) and extract one shared deduplication component used by both flows instead of duplicating the key logic.

### Affected areas

src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py (modified); src/guidami_ai_patente_ingestor/services/quiz/ (flatten_quiz.py simplified, new deduplicate_quiz_items.py, __init__.py export); src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py (docstring updated — replaces the `_dedup_enriched_quiz` reference with `DeduplicateQuizItems`); tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py (modified) and test_deduplicate_quiz_items.py (new); tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py and test_quiz_preparation_flows_v2.py (updated); docs/architecture/modules/ingestor/quiz_pipelines.md, _index.md, patterns.md (revised)

### Success criteria

build_quiz_cleaning_flow and build_quiz_indexing_flow both compose flatten/map/dedup as separate named transforms visible in the ApplyStep call, not hidden inside one mega-class; dedup key logic exists in exactly one shared place used by both flows; existing dedup behavior and flow outputs unchanged; full test suite green including new tests for extracted components

## Non-goals

No change to dedup semantics or flow outputs (same key: normalized text + correct_answer + image); no schema/API changes; no change to build_quiz_enrichment_flow, embed_step, or store_step; no new CLI commands or public behavior changes.

## Decisions

1. **Promote the shared dedup logic to a `services/quiz/` class, `DeduplicateQuizItems`, instead of a bare per-flow function** — the same triple key `(text.strip(), correct_answer, image)` is currently duplicated in two places (`FlattenQuiz.execute` and the private `_dedup_enriched_quiz` in `orchestrators/quiz_flows.py`). `docs/architecture/modules/ingestor/quiz_pipelines.md` documents a prior decision to keep this kind of transform as a bare orchestrator function specifically because it had a single call site. That premise no longer holds once the same logic is shared by two flow builders (`build_quiz_cleaning_flow` and `build_quiz_indexing_flow`); a shared, independently testable class is the better home. This plan's documentation task explicitly revises that prior decision rather than leaving it contradicted.
2. **`DeduplicateQuizItems` is generic and Protocol-typed, not model-specific** — `class DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]])`, where `_QuizItemLike` is a structural `Protocol` (`text: str`, `correct_answer: bool`, `image: str | None`, `number: str`). Both `CleanedQuizModel` and `EnrichedQuizModel` already satisfy this Protocol structurally — no model changes needed. Uses PEP 695 generic syntax (Python 3.12+, per project convention) and reuses `commons.utils.deduplicate` internally, mirroring the `_dedup_key`/`_log_duplicate` staticmethod pattern already established by `FlattenQuiz`.
3. **`FlattenQuiz` keeps its file/class but drops dedup** — `FlattenQuiz.execute()` becomes unnest + map only (delegates each `(sub_question, parent)` pair to `QuizMapper.from_parsed_to_cleaned`). Dedup is removed from this class entirely and now happens as a second, separate transform chained after it. The class is not renamed: "flatten" still accurately describes unnest+map; only the dedup responsibility moves out.
4. **Both flows chain dedup via `ApplyStep`, mirroring the existing `map_to_embeddable` pattern**:
   - `build_quiz_cleaning_flow`: `ApplyStep("flatten_quiz", FlattenQuiz(), DeduplicateQuizItems(), input_key=..., output_key=...)`
   - `build_quiz_indexing_flow`: `ApplyStep("map_to_embeddable", DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable), input_key=..., output_key=...)`
   Step names in both flows are unchanged, so existing flow-shape tests (`test_flow_has_five_steps_in_order`, `test_cleaning_flow_has_three_steps_in_order`) do not need to change.
5. **Unify the duplicate-skip log message** to `"skipping duplicate quiz item %s"` (logging `item.number`) for both flows. The current `FlattenQuiz` message additionally logs `question_id`, which is not part of `_QuizItemLike` — this detail is dropped. This is a diagnostic-only change (log wording), not a change to dedup semantics or flow output.
6. **Documentation revision is an explicit implementation task, not just the standard post-implementation `doc-architect` pass** — `quiz_pipelines.md` currently states the now-superseded rationale in its own words; it must be corrected to describe `DeduplicateQuizItems` and explain why the earlier bare-function decision no longer applies, rather than leaving two contradictory decisions on record. This necessarily means `_dedup_enriched_quiz` stays named in the corrected text, framed as history ("first lived as a bare function, then was superseded once a second call site appeared") rather than as current state — the DoD check below verifies the new state is documented, not the absence of the old name.

## Open questions / Risks

- **Risk (low): PEP 695 generic class bound to a `Protocol`.** `class DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]])` combines a type-parameter bound with a `Protocol` and a generic `ABC` base (`UseCase`). This combination isn't used elsewhere yet in the codebase (existing generics — `ForEach[T, U]` — are not `Protocol`-bound). Mitigated by `uv run pyright` in the Definition of Done; if pyright rejects the bound-generic form, fall back to an unbound `DeduplicateQuizItems(UseCase[list[Any], list[Any]])` with the Protocol used only for the internal key/log helpers' parameter types.

## Implementation tasks

### 1. Add `DeduplicateQuizItems`

Create `src/guidami_ai_patente_ingestor/services/quiz/deduplicate_quiz_items.py`:
- `_QuizItemLike(Protocol)` — structural fields `text: str`, `correct_answer: bool`, `image: str | None`, `number: str`.
- `DeduplicateQuizItems[T: _QuizItemLike](UseCase[list[T], list[T]])` — `execute` deduplicates via `commons.utils.deduplicate`, key `(item.text.strip(), item.correct_answer, item.image)`, `on_duplicate` logs `logger.warning("skipping duplicate quiz item %s", item.number)`.

Export `DeduplicateQuizItems` from `src/guidami_ai_patente_ingestor/services/quiz/__init__.py`.

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
- Add: `tests/guidami_ai_patente_ingestor/services/quiz/test_deduplicate_quiz_items.py::test_empty_input_returns_empty_list`
- Add: `tests/.../test_deduplicate_quiz_items.py::test_no_duplicates_all_preserved`
- Add: `tests/.../test_deduplicate_quiz_items.py::test_duplicates_by_stripped_text_answer_image_are_removed`
- Add: `tests/.../test_deduplicate_quiz_items.py::test_same_text_different_image_both_kept`
- Add: `tests/.../test_deduplicate_quiz_items.py::test_same_text_different_correct_answer_both_kept`
- Add: `tests/.../test_deduplicate_quiz_items.py::test_works_on_cleaned_quiz_model` and `::test_works_on_enriched_quiz_model` — proves the same component dedups both model types structurally, without a model-specific subclass

### 2. Simplify `FlattenQuiz` to unnest+map only

Modify `src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py`: remove the `deduplicate(...)` call and the `_dedup_key`/`_log_duplicate` staticmethods from `FlattenQuiz.execute`; keep `_flatten` (unnest) and the per-pair `QuizMapper.from_parsed_to_cleaned` mapping. Update the class docstring to no longer claim dedup responsibility.

**Tests** (intent, not contract):
- Modify: `tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py` — remove `test_duplicates_by_stripped_text_answer_image_are_deduplicated`, `test_same_text_different_image_both_kept`, `test_same_text_different_correct_answer_both_kept` (dedup is no longer `FlattenQuiz`'s responsibility; equivalent coverage now lives in `test_deduplicate_quiz_items.py`)
- Keep: `test_empty_input_returns_empty_list`, `test_no_duplicates_all_preserved_and_mapped_to_cleaned_quiz_model`, `test_multiple_main_questions_all_sub_questions_flattened` — still valid, unaffected by dedup removal

### 3. Wire `DeduplicateQuizItems` into both flows

Modify `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py`:
- Remove `_dedup_enriched_quiz` and the now-unused `from commons.utils import deduplicate` import.
- Import `DeduplicateQuizItems` from `guidami_ai_patente_ingestor.services.quiz`.
- `build_quiz_cleaning_flow`: change `flatten_step` to `ApplyStep("flatten_quiz", FlattenQuiz(), DeduplicateQuizItems(), ...)`.
- `build_quiz_indexing_flow`: change `map_to_embeddable_step` to `ApplyStep("map_to_embeddable", DeduplicateQuizItems(), ForEach(QuizMapper.from_enriched_to_embeddable), ...)`.
- Update the module/function docstrings that describe the old `_dedup_enriched_quiz`-based chain.
- Update `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py`'s `QuizMapper` class docstring: it currently names `_dedup_enriched_quiz` as the place flatten+dedup lives outside the mapper — replace with a reference to `DeduplicateQuizItems`.

**Tests** (intent, not contract):
- Remove: `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py::test_dedup_empty_input_returns_empty_list`, `::test_dedup_no_duplicates_all_preserved`, `::test_dedup_duplicates_by_stripped_text_answer_image_are_removed`, `::test_dedup_same_text_different_image_both_kept`, `::test_dedup_same_text_different_correct_answer_both_kept`, and the `_dedup_enriched_quiz` import (coverage moved to `test_deduplicate_quiz_items.py`)
- Keep: `test_flow_has_five_steps_in_order` and all other flow-shape tests in `test_quiz_flows.py` — step names unchanged
- Modify: `tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py::test_cleaning_flow_has_three_steps_in_order` — update the docstring comment (`"La catena è LoadParsedQuiz -> FlattenQuiz -> WriteCleanedQuiz"`) to mention the dedup step now chained after `FlattenQuiz`; assertion itself is unchanged (step names unaffected)

### 4. Revise the documented architectural decision

Invoke the `doc-architect` agent (after 1–3 are implemented) with the concrete diff, explicitly asking it to correct — not just append to — the section of `docs/architecture/modules/ingestor/quiz_pipelines.md` that documents `_dedup_enriched_quiz` as a deliberately bare orchestrator function. It must record: `DeduplicateQuizItems` now lives in `services/quiz/`, is generic/Protocol-typed, and is shared by both `build_quiz_cleaning_flow` and `build_quiz_indexing_flow`; the earlier decision applied only while the logic had a single call site. Also check `docs/architecture/modules/ingestor/_index.md` and `docs/architecture/patterns.md` for the same now-outdated references (`_dedup_enriched_quiz`, `FlattenQuiz` doing dedup) and correct them.

**Tests**: none (documentation-only task); verified via the DoD grep checks below instead.

## Definition of Done

Variable block (plan-specific):

- [x] `grep -rn "_dedup_enriched_quiz" src tests` returns nothing
- [x] `grep -n "class DeduplicateQuizItems" src/guidami_ai_patente_ingestor/services/quiz/deduplicate_quiz_items.py` matches
- [x] `uv run python -c "from guidami_ai_patente_ingestor.services.quiz import DeduplicateQuizItems"` succeeds
- [x] `grep -n "deduplicate" src/guidami_ai_patente_ingestor/services/quiz/flatten_quiz.py` returns nothing (dedup removed from `FlattenQuiz`)
- [x] `uv run pytest tests/guidami_ai_patente_ingestor/services/quiz/test_deduplicate_quiz_items.py tests/guidami_ai_patente_ingestor/services/quiz/test_flatten_quiz.py tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_flows.py tests/guidami_ai_patente_ingestor/orchestrators/test_quiz_preparation_flows_v2.py -v` passes
- [x] `grep -n "class DeduplicateQuizItems" docs/architecture/modules/ingestor/quiz_pipelines.md` matches (new shared service documented as current state; historical mentions of `_dedup_enriched_quiz` narrating the reversal are expected and acceptable — see Decisions)

Fixed block (same for every plan):

- [x] `uv run pytest` green (including new tests)
- [x] `uv run pyright` clean
- [x] `uv run ruff check src tests` clean
- [x] Agent `doc-architect` invoked (if available) — not registered as an invokable subagent type in this environment; ran via `general-purpose` explicitly instructed to follow `.claude/agents/doc-architect.md`'s procedure and constraints verbatim (doc-reader-only reads, incremental edits, index updates)
- [x] Plan updated to `status: Implemented`
