# SP04-tris — Quiz mapper consolidation (single `QuizMapper`)

## STATUS

✅ **Implemented (2026-06-24).**

* `mappers/quiz/quiz_mapper.py` (`QuizMapper`): `from_enriched_quiz_item_to_embeddable`,
  `from_embeddable_to_quiz_question`, `_image_filename`. Old `QuizQuestionMapper` /
  `EmbeddableQuizQuestionMapper` deleted; `mappers/quiz/__init__.py` re-exports `QuizMapper` only.
* `MapToEmbeddableStep`: flatten+dedup moved into a private static helper
  (`_flatten_and_dedup`), delegating per-item to `QuizMapper.from_enriched_quiz_item_to_embeddable`.
  Same dedup key `(text.strip(), correct_answer, image)`.
* `MapToQuizEntityStep`: uses `QuizMapper.from_embeddable_to_quiz_question`.
* Tests: `test_quiz_question_mapper.py` + `test_embeddable_quiz_question_mapper.py` replaced by
  a single `test_quiz_mapper.py` (1:1 methods, no dedup). Dedup cases moved into
  `test_map_to_embeddable_step.py` (real flatten+dedup, not mocked) alongside one
  delegation-to-mapper test (mocked).
* `quiz_flows.py` required no changes (imports steps, not mappers) — verified.
* Suite unit green: 197 passed, 13 deselected (integration). `ruff check`/`ruff format --check`/
  `pyright` clean on all touched files.
* No behavior change: same dedup semantics, same field mappings — confirmed by reusing the
  original test assertions.

## Single purpose

Consolidate the two existing quiz mappers (`QuizQuestionMapper`, `EmbeddableQuizQuestionMapper`) into a single `QuizMapper` (1:1 static methods) and **move the flatten+dedup** from the mapper to the step (`MapToEmbeddableStep`). It is a **behavior-preserving** refactor (consolidation + relocation of responsibilities, no logic change): it operates on the model names already renamed by SP04-bis.

## Depends on / enables

* **Depends on** SP04-bis (implemented): the models are already renamed (`QuizBankModel`, `EnrichedQuizModel`/`EnrichedQuizItemModel`, `EmbeddableQuizModel`).
* **Enables** SP06 (extends `QuizMapper` with base-map source→enriched methods) and SP08 (extracts flatten+dedup from the step into an injected service, on the mapper already consolidated here).
* Must be executed **before** SP06 and SP08, **after** SP04-bis.

## Starting precondition (gate)

> ⛔ **Do not start implementation until SP04-bis is ✅ implemented (green suite + merged).**
> SP04-tris operates on the model names already renamed by SP04-bis; starting beforehand would create naming/merge conflicts.

## Motivation (what is wrong today)

1. The **mapping sequence** is not documented: two distinct mappers (`QuizQuestionMapper`, `EmbeddableQuizQuestionMapper`) fragment the transformation chain across different points in the code; it needs to be made explicit as a backbone in a single class.

## Single `QuizMapper` (decision 2026-06-23)

A single `QuizMapper` class (`mappers/quiz/quiz_mapper.py`) gathers **all** layer transitions, making the chain visible in a single file. **Methods contract**: all `@staticmethod`, each takes **one** model and produces **another** (1:1), with any **extra arguments** to be injected into the new object. Replaces the two current mappers (`QuizQuestionMapper`, `EmbeddableQuizQuestionMapper`).

| Method (`QuizMapper.…`) | Signature | In | Notes |
| --- | --- | --- | --- |
| `from_quiz_bank_item_to_enriched` | `(item: QuizBankItemModel) -> EnrichedQuizItemModel` | SP06 | base-map, `image_description=None`; **added by SP06** |
| `from_quiz_bank_to_enriched` | `(model: QuizBankModel) -> EnrichedQuizModel` | SP06 | uses the item-level method; **added by SP06** |
| `from_enriched_quiz_item_to_embeddable` | `(item: EnrichedQuizItemModel, parent: EnrichedQuizModel) -> EmbeddableQuizModel` | **SP04-tris** | extra arg `parent` → `question_id`/`topic`; `image_filename` from `item.image` |
| `from_embeddable_to_quiz_question` | `(model: EmbeddableQuizModel) -> QuizQuestion` | **SP04-tris** | discards `image_description`, keeps `embedding` |

> **SRP Trade-off (accepted).** A single class for all transitions changes for multiple reasons (SRP weaker than class-per-transition); the choice prioritizes the **readability of the chain in a single place**. Mitigation: small, static, pure methods.
> **flatten+dedup is NOT in the mapper.** It is not a 1:1 map (collection operation + dedup rule) → lives in the Step (see below). `QuizMapper` remains solely 1:1 translation.
> **Enrichment and OCP.** The base-map (SP06) produces `EnrichedQuizModel` with the enrichment fields set to `None`; the enrichers (SP06, Open/Closed) populate them via `model_copy(update=…)`. Thus, adding an agent does **not** modify the mapper's signature (no per-agent arguments in the base-map).

## Files (move / rename / edit)

### Mapper (`mappers/quiz/`) — consolidation into `QuizMapper`

* **NEW** `quiz_mapper.py` (`QuizMapper`): brings over `from_enriched_quiz_item_to_embeddable` (item-level, **without** flatten/dedup) and `from_embeddable_to_quiz_question`. The `from_quiz_bank_*` methods are added by SP06.
* **DELETE** `quiz_question_mapper.py` (`QuizQuestionMapper`): the 1:1 item→embeddable map migrates into `QuizMapper`; the **flatten+dedup** migrates into `MapToEmbeddableStep`.
* **DELETE** `embeddable_quiz_question_mapper.py` (`EmbeddableQuizQuestionMapper`): `to_entity` → `QuizMapper.from_embeddable_to_quiz_question`.
* `mappers/quiz/__init__.py`: re-export `QuizMapper` (remove the two old ones).

### Step (`orchestrators/steps/quiz/`)

The **step names remain** (they are orchestration):

* `map_to_embeddable_step.py`: **now hosts flatten+dedup** (previously in the mapper). `execute` reads `ENRICHED_QUIZ`, iterates `model.sub_questions`, deduplicates on the key `(text.strip(), correct_answer, image)` and for each kept item calls `QuizMapper.from_enriched_quiz_item_to_embeddable(item, model)`; writes `EMBEDDABLE_QUIZ`. Loop+dedup in a private step helper.
* ⚠️ *Step is no longer purely thin*: it hosts a domain rule (dedup). Trade-off accepted (explicit choice); the dedup remains small, isolated in the private helper, and tested.


* `map_to_quiz_entity_step.py`: uses `QuizMapper.from_embeddable_to_quiz_question`.
* `quiz_flows.py`: no changes expected (imports steps, not models/mappers) — verify nonetheless.

### Tests (update names, **same assertions**)

* `mappers/quiz/test_quiz_question_mapper.py` + `test_embeddable_quiz_question_mapper.py` → **a single** `test_quiz_mapper.py` (1:1 methods of `QuizMapper`). The **dedup** tests are no longer here: they migrate to `test_map_to_embeddable_step.py`.
* `orchestrators/steps/quiz/test_map_to_embeddable_step.py`: add the **flatten+dedup** cases (e.g., 3 sub-questions, 2 distinct → 2 embeddable) alongside the delegation to the mapper.
* `test_map_to_quiz_entity_step.py`: update imports/names.

## TDD (behavior-preserving refactor)

1. Run the suite **before** (green) as a baseline.
2. Apply the consolidation per module, maintaining the **same assertions** on the behavior. For 1:1 mappers, only the symbol changes; for **dedup**, the assertions move from the mapper test to `test_map_to_embeddable_step.py` (same logic, new location).
3. Suite **unit** green **after** (this is the behavior-preserving baseline: there is no quiz integration test nor `enriched` data on disk):
* flatten+dedup (now in `MapToEmbeddableStep`): same post-dedup count as the unit assertions (logic moved, not changed);
* ⚠️ the e2e integration (`quiz_questions` count 7098) **does not exist today** (only unit tests; no `data/enriched/quiz-patente-ab/`) → it is not a baseline for this refactor; it will be verified in **SP07** after SP06 produces the enriched data.


4. `ruff check` + `pyright` 0 errors on touched files.

> No new behavior tests: it's a refactor. If a test fails for reasons other than the consolidation, **stop and report** (it might reveal hidden coupling).

## Done criteria

* Single `QuizMapper` (1:1 `from→to` static methods); old `QuizQuestionMapper`/`EmbeddableQuizQuestionMapper` removed; flatten+dedup moved to `MapToEmbeddableStep`; re-exports updated in all `__init__.py` files.
* SP04 (step + flow) compiles and runs with the consolidated mapper; `context_keys` **does not** change (keys are strings, independent of class names).
* Suite **unit** green (baseline = unit; the quiz integration does not exist yet); 7098 e2e verified in SP07 after SP06. ruff/pyright clean.
* `index.md` updated (line + DAG).

## DAG Update (in `index.md`)

```
01 ─► 02 ─►┬─ 03 (knowledge index) ─┐
           ├─ 04 ─► 04-bis (data model) ─► 04-tris (mapper) ─┐
           └─ 05 (knowledge prep+runner) ────────────────► 06 (quiz prep) ─┘ ─► 07 (CLI + cleanup + doc)

```

04-tris depends on 04-bis (operates on the already renamed models) and is a **prerequisite for 06 and 08**.