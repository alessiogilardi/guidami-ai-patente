# SP04-bis — Quiz Data Model Alignment (Explicit Sequence)

> **Status: ✅ COMPLETED** (2026-06-23). All models renamed, source DTOs moved to `models/quiz/`,
> `entities/` contains only `Article`. 58 quiz tests green, ruff clean. Enables `04-tris`.

## Single Purpose

Make the quiz data model chain **explicit and consistent** across the 4 stages (`source` → `enriched` → `embeddable` → `db row`): a naming convention that telegraphs stage and shape, relocating source DTOs outside of `entities/`. It is a **behavior-preserving** refactor (rename + move, no logic change): a prerequisite for `SP04-tris`, reviewing the code already implemented in `SP04`.

> ℹ️ The mapper consolidation + `flatten+dedup` move is now in `04-tris`; `SP04-bis` is a pure rename (old mappers remain, updated to the new model names).

## Depends On / Enables

* **Depends on** `SP04` (implemented): renames its models/mappers/steps.
* **Enables** `04-tris`: the mapper consolidation operates on the model names already renamed here.
* Must be executed **before** `04-tris` and **after** `SP04`.

## Starting Precondition (Gate)

> ⛔ **Do not start implementation until `SP04` is ✅ implemented (green suite + merged).**
> `SP04` is ✅ (2026-06-22) → gate satisfied. The output of `SP04-bis` (renamed models, green and merged) is in turn the **starting gate for `04-tris**`.

## Motivation (What's Wrong Today)

1. `QuizMainQuestion`/`QuizSubQuestion` are **unpersisted source DTOs** but they live in `entities/` → violates the "entities = 1:1 mirror of DB table" convention (the only quiz table is `quiz_questions` → `QuizQuestion`). They belong in `models/quiz/`.
2. The naming does not indicate the stage: two "Main/Sub" pairs (`source` + `enriched`) that later collapse into a flat `EmbeddableQuizQuestion` → the **nested → flat** transition (`flatten+dedup`) is implicit.

> **Out of scope (follow-up knowledge):** `Article` has the same flaw (source DTO in `entities/`). Based on the decision made ("quiz only" scope), it is **not** touched here; flagged for future knowledge domain alignment.

## Adopted Convention (Decision 2026-06-23)

**`*Model` = unpersisted intermediate (`models/quiz/`); `*` entity = DB row (`entities/`).**
Stage-explicit naming with the `Model` suffix on intermediates.

> **Terminological Note (Clean Architecture).** Here "entity" means *persistence row model* (project convention: 1:1 mirror of a DB table), **not** the Clean Architecture Entity (Critical Business Rules + Data, framework-independent — ch20). `QuizQuestion`, with `embedding` and `embedded_text`, is in a CA sense a persistence/ML data structure, not a domain Entity. The project convention is internal and consciously divergent from CA; the plan is consistent with it.

## Canonical Sequence (Backbone of the Plan)

```text
source (layer "cleaned", nested)
   QuizBankModel ─┬─ sub_questions: list[QuizBankItemModel]
        │ enrich  → base-map QuizMapper.from_quiz_bank_to_enriched
        │          + enricher (SP06) fill fields via model_copy
        ▼
enriched (layer "enriched", nested)
   EnrichedQuizModel ─┬─ sub_questions: list[EnrichedQuizItemModel]   (+ image_description)
        │ flatten + dedup  → MapToEmbeddableStep (loop + dedup)
        │                    uses QuizMapper.from_enriched_quiz_item_to_embeddable(item, parent)
        ▼
embeddable (flat, one row per item, Embedded protocol)
   EmbeddableQuizModel   (image_description, embedding, embedded_text)
        │ embed (EmbedStep) → embedding populated
        │ to_entity  → QuizMapper.from_embeddable_to_quiz_question
        ▼
db row (flat)
   QuizQuestion   [ENTITY, commons/entities/quiz — unchanged]

```

> **Field Note (NO field renames):** field names (`question_id`, `topic`, `sub_questions`, `number`, `text`, `correct_answer`, `image`, `image_description`, `image_filename`, `embedding`) **remain unchanged** to preserve the JSON contract on disk (round-trip `enriched` read/write between `SP06` and `SP04`). **Only the classes** are renamed.

## Rename Mapping (Classes)

| Old | New | Shape | Notes |
| --- | --- | --- | --- |
| `QuizMainQuestion` | `QuizBankModel` | nested | **move** `entities/` → `models/quiz/` |
| `QuizSubQuestion` | `QuizBankItemModel` | nested (child) | ditto |
| `EnrichedQuizMainQuestion` | `EnrichedQuizModel` | nested | `models/quiz/` |
| `EnrichedQuizSubQuestion` | `EnrichedQuizItemModel` | nested (child) | `models/quiz/` |
| `EmbeddableQuizQuestion` | `EmbeddableQuizModel` | flat | `models/quiz/`; remains Embedded |
| `QuizQuestion` | `QuizQuestion` | flat | **unchanged** (DB entity) |

## Files (Move / Rename / Edit)

### Model (`models/quiz/`)

* **MOVE** `entities/quiz_bank.py` → `models/quiz/quiz_bank.py` (`QuizBankModel` + `QuizBankItemModel`; field `items` → **remains `sub_questions**`).
* **RENAME** `models/quiz/enriched_quiz_bank.py` → `models/quiz/enriched_quiz.py` (`EnrichedQuizModel` + `EnrichedQuizItemModel`).
* **RENAME** `models/quiz/embeddable_quiz_question.py` → `models/quiz/embeddable_quiz.py` (`EmbeddableQuizModel`).
* `models/quiz/__init__.py`: re-export new names (remove old ones).
* `entities/__init__.py`: **remove** `QuizMainQuestion`/`QuizSubQuestion` (keep `Article`).

> The parent+child pair remains in the same file (practice already present in the project, parent and child are tightly coupled). A rigid one-class-per-file rule would break cohesion without any benefit.

### Repository (`repositories/json/`)

* `quiz_bank_repository.py`: import from `models.quiz import QuizBankModel`; `JsonRepository[QuizBankModel]` (repo name `QuizBankRepository` unchanged).
* `enriched_quiz_bank_repository.py`: `JsonRepository[EnrichedQuizModel]` (repo name `EnrichedQuizBankRepository` unchanged). Also replace placeholder docstrings mentioning `Article`.

### Step SP04 (Implemented Code — `orchestrators/steps/quiz/`)

The **step names and their structure remain unchanged** (this plan does not touch mappers/steps, only type-refs to renamed models):

* `load_enriched_quiz_step.py`: type-ref `EnrichedQuizMainQuestion` → `EnrichedQuizModel`.
* `map_to_embeddable_step.py`: type-refs to renamed models (`EnrichedQuizMainQuestion` → `EnrichedQuizModel`, `EmbeddableQuizQuestion` → `EmbeddableQuizModel`); internal structure (`flatten+dedup` in the `QuizQuestionMapper`, unchanged here) **does not** change.
* `map_to_quiz_entity_step.py`: type-ref `EmbeddableQuizQuestion` → `EmbeddableQuizModel`; continues using the existing mapper `EmbeddableQuizQuestionMapper` (unchanged here).
* `quiz_flows.py`: no modifications expected (imports steps, not models) — verify anyway.

### Existing Mappers (`mappers/quiz/`) — Type-Ref Updates Only

> Mappers **are not restructured here** (consolidation is `04-tris`). `QuizQuestionMapper` and `EmbeddableQuizQuestionMapper` **remain** distinct classes; only references to the renamed model names are updated.

* `quiz_question_mapper.py` (`QuizQuestionMapper`): type-refs to renamed models (`EnrichedQuizMainQuestion`/`EnrichedQuizSubQuestion` → `EnrichedQuizModel`/`EnrichedQuizItemModel`, `EmbeddableQuizQuestion` → `EmbeddableQuizModel`); the **`flatten+dedup` stays inside** `QuizQuestionMapper` (structure is untouched).
* `embeddable_quiz_question_mapper.py` (`EmbeddableQuizQuestionMapper`): type-ref `EmbeddableQuizQuestion` → `EmbeddableQuizModel`.
* `mappers/quiz/__init__.py`: unchanged re-export (same two mappers, just potential updates to internal imports within the files).

### Tests (Update Names, **Same Assertions**)

* `mappers/quiz/test_quiz_question_mapper.py` + `test_embeddable_quiz_question_mapper.py`: update the model names used in tests, **structure and assertions unchanged** (including the dedup test, which remains here).
* `models/quiz/test_embeddable_quiz_question.py` → `test_embeddable_quiz.py`.
* `orchestrators/steps/quiz/test_map_to_embeddable_step.py`, `repositories/test_enriched_quiz_bank_repository.py`, `orchestrators/steps/quiz/test_load_enriched_quiz_step.py`, `test_map_to_quiz_entity_step.py`: update imports/model names, structure unchanged.

### Doc (References — Update Names)

* `plans/ingest--orchestrator/04-quiz-indexing-flow.md`: note at the top "models renamed from `SP04-bis`" + update names in the sections.
* `plans/ingest--orchestrator/06-quiz-preparation-flow.md`: already uses the new names (aligned in this session) + dependency on `SP04-bis` (models) and `04-tris` (mappers).
* `.claude/architectures/ingestor/*`: **do not** modify manually → the `architecture-doc-keeper` agent will realign them at the end of implementation (procedure from `CLAUDE.md`).

---

## TDD (Behavior-Preserving Refactor)

1. Execute the suite **before** (green) as a baseline.
2. Apply rename/move per module, maintaining the **same assertions** on behavior: only the symbol changes, the mapper/step structure remains the same as `SP04`.
3. **Unit** suite green **after** (this is the behavior-preserving baseline: there is no quiz integration test nor `enriched` data on disk).
4. ⚠️ The e2e integration (`quiz_questions` count 7098) **does not exist today** (unit tests only; no `data/enriched/quiz-patente-ab/`) → it is not a baseline for this refactor; it is verified in **SP07** after SP06 produces the `enriched` data.
5. `ruff check` + `pyright` 0 errors on touched files.

> No new behavioral tests: this is a rename. If a test fails for reasons other than the renamed symbol, **stop and report** (it might reveal hidden coupling).

---

## Done Criteria

* Quiz source DTOs moved to `models/quiz/`; `entities/` on the ingestor side contains only `Article`.
* Consistent renamed chain: `QuizBankModel`/`QuizBankItemModel` → `EnrichedQuizModel`/`EnrichedQuizItemModel` → `EmbeddableQuizModel` → `QuizQuestion`.
* Existing mappers (`QuizQuestionMapper`, `EmbeddableQuizQuestionMapper`) **remain** distinct classes, updated to the new model names; no change in structure/responsibility.
* `SP04` (steps + flows) compiles and runs with the new names; `context_keys` **does not** change (keys are strings, independent of class names).
* **Unit** suite green (baseline = unit; quiz integration doesn't exist yet); 7098 e2e verified in SP07 after SP06. `ruff`/`pyright` clean.
* `plans/04` and `plans/06` aligned with the new names; `index.md` updated (row + `DAG`).
* `Article` follow-up logged (not executed).

---

## DAG Update (in `index.md`)

```text
01 ─► 02 ─►┬─ 03 (knowledge index) ─┐
           ├─ 04 ─► 04-bis (data model) ─► 04-tris (mapper) ─┐
           └─ 05 (knowledge prep+runner) ────────────────► 06 (quiz prep) ─┘ ─► 07 (CLI + cleanup + doc)

```

`04-bis` depends on `04` (renames its code) and is a **prerequisite for `04-tris**`.