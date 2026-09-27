<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose:
draft → ready at sign-off; ready → in-progress when the first plan is extracted;
in-progress → implemented once the Definition of Done is verified.
-->

# Spec 0023: Answer-aware image descriptions and targeted regeneration

| | |
|---|---|
| **Id** | 0023 |
| **Status** | draft |
| **Date** | 2026-09-27 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`; no separate transcript file) |
| **Supersedes / superseded by** | Supersedes ADR 0001 (road sign describer stays answer-blind) once accepted |

## Problem & Motivation

`quiz_images.description` (produced by `RoadSignDescriberAgent` during `ingest prepare
quiz`, persisted by `ingest index quiz`) misidentifies some figures. Observed on
2026-09-27 while tuning the explanation writer:

- Question **21137** ("Il semaforo di onda verde in figura si trova su strade con più
  incroci…", correct answer **Vero**): the stored description reads "Pannello
  integrativo con indicazione di velocità massime… ma non sono semafori" — the green-wave
  speed panel is misread as a speed-limit panel, and the description contradicts a true
  statement.

A wrong description does not stay local. `image_description` feeds:

- the question embeddings (`QuizMapper.from_enriched_to_embedded`), hence retrieval;
- the comma judge (`CommaLabelerRequest`), hence which commas a labeling selects — 21137's
  labeling picked commas about the "preavviso di semaforo", plausibly because of it;
- the glossary stages and the explanation writer.

Two causes, both addressed here:

1. **The describer is answer-blind** (ADR 0001). It sees every quiz text that uses the
   image but not which are true, so on an ambiguous figure it has no way to tell the
   distractors from the facts. ADR 0001 feared motivated reasoning — a model told a
   statement is false hallucinating a contradicting detail. That risk was framed around
   one statement; the actual data has **427 images for 4147 questions, 9.7 questions per
   image on average (max 54), and 341/427 images carry both true and false statements**.
   With ~10 labeled statements per figure, the true ones pin the figure's identity and no
   single false one can steer the description.
2. **The model is the weakest in its family** (`gemini-2.5-flash-lite`). Recognising
   uncommon signs is primarily a vision-quality problem.

There is also no way to regenerate descriptions alone: `prepare quiz --force` restarts
from `cleaned/` and re-runs `NormReferenceDescriberAgent` on all 7099 quizzes too
(cost, and churn on unrelated fields in the committed `data/enriched/` files).

Finally, regenerated descriptions would silently leave every existing labeling of an
image question computed against the old description: the labeling configuration epoch
(`judge_model`, `prompt_version`, `candidate_variant`, `dense_k`, `text_k`,
`lexeme_fields`) does not cover it.

## Functional Requirements

### FR-1: The describer receives every statement with its correct answer

`QuizContextModel` replaces `texts: list[str]` with a list of statements, each carrying
its text and `correct_answer: bool`. `RoadSignDescriberMapper.from_enriched_quizzes_to_request`
carries `EnrichedQuizModel.correct_answer` through; its existing deduplication
(first-seen `(topic, text)`, then global text dedup, first-seen topic wins) is unchanged.
`contexts_block` renders each statement marked with its answer, e.g.
`- (Vero) Il semaforo di onda verde in figura…`.

### FR-2: The describer prompt uses the labels without being steered by them

`configs/agents/road_sign_describer.yaml`:

- The labeled statements stay inside the existing `<contesti_quiz>` tag, which the system
  prompt names and declares as data to evaluate, not instructions.
- States that `(Vero)` statements are certain facts about the figure and identify it;
  `(Falso)` statements are distractors and only say what the figure is *not*.
- Forbids inventing a visual detail to refute a false statement: describe only what is
  visible.
- On conflict between what the model sees and a true statement, the true statements win
  for `name` (identification); `visual_analysis`/`description` stay cautious rather
  than asserting the contradicting reading.
- The existing three-case taxonomy (single sign / driving scene / signs in sequence),
  the JSON field order, and the `visual_analysis`/`name`/`description` role split are
  unchanged.

### FR-3: The describer runs on `gemini-3.8-flash`

`model_name: openrouter/google/gemini-3.8-flash` in `road_sign_describer.yaml`. No other
agent changes model.

### FR-4: `uv run ingest prepare quiz --only image-descriptions [--image FILE]… [--dry-run]`

A targeted regeneration mode of `prepare quiz`:

- Loads the whole `enriched` layer (not `cleaned`), so grouping by image always sees every
  question that uses it — contexts are never partial.
- Runs `ImageDescriptionEnricherService` only (reused unchanged); never runs
  `NormReferenceEnricherService`.
- No `FilterAlreadyDoneStep`: this mode is a regeneration by definition. `--force` is
  rejected together with `--only` (usage error), since it has no meaning here.
- `--image FILE` (repeatable) restricts the described images to the named filenames;
  only the questions using those images are rewritten. An unknown filename is a usage
  error listing the unknown names, not a silent no-op.
- Rewrites only the enriched files of the affected questions, changing only
  `image_description` and `image_analysis` (`RoadSignDescriberMapper.from_response_to_enriched_quiz`
  already sets exactly those two fields).
- A failed description keeps today's per-image degrade (warning, question passes through
  untouched) — so the question keeps its *old* description rather than losing it.
- Calls are tracked in `llm_call_logs` like every other `prepare` run; logs go to
  `logs/ingest_prepare_<ts>/run.log`.
- `--dry-run` prints the step chain and the image count/filter, with no filesystem write,
  LLM call or DB connection — same guarantee as today's `--dry-run`.

### FR-5: `index quiz` invalidates labelings computed against a changed description

A new `InvalidateStaleLabelingsStep`, placed immediately before `StoreQuizStep` in
`build_quiz_indexing_flow`:

- Reads the current `quiz_images.description` for the images in this run's
  `QUIZ_IMAGE_ENTITIES` and compares with the incoming description.
- For every question whose image's description changed (or which had none before and
  now has one), deletes its `quiz_labelings` rows **not** validated by a human
  (`validated_at IS NULL`), with their `quiz_comma_labels`.
- Human-validated labelings on a changed image are never deleted; the step logs a
  `warning` with their count.
- Logs an `info` line with the number of changed images and deleted labelings; does
  nothing (and deletes nothing) when no description changed.
- Deleted labelings are recomputed on demand by `POST /quiz-questions/{number}/label`
  (spec 0017) — no batch relabel is part of this spec.

## Non-Goals

- **No automated description-quality evaluation.** Discussed and explicitly dropped by
  the user on 2026-09-27: validation is a manual review of a sample (see Testing).
- **No change to `NormReferenceDescriberAgent`**, its prompt or its fields.
- **No change to the labeling epoch definition**, and no batch relabel run.
- **No change to the explanation writer, the API, or the bot.** Telegram Markdown
  rendering is a separate, later spec (decision already taken: minimal Markdown from the
  LLM, converted to Telegram HTML by the bot).
- **No reconciliation of orphaned `quiz_images` rows** (still deferred, spec 0008).

## Architectural Decisions

### AD-1: The describer becomes answer-aware (supersedes ADR 0001)

Alternatives: stay blind and only change model; pass only the true statements. Chosen:
pass every statement labeled. Rationale in Problem & Motivation (§1): multiple, mostly
mixed statements per image make single-statement steering implausible, and true
statements are the strongest identification signal available. "Only true statements"
was rejected because images whose statements are all false would get no context at all.
To be recorded as a new ADR via `second-brain:adr`, marking ADR 0001 superseded.

### AD-2: A targeted mode on `prepare quiz`, not `--force` and not manual deletion

`--force` re-runs the norm-reference enrichment on 7099 quizzes and churns unrelated
committed fields; deleting enriched files by hand re-runs it on ~4100 and is error-prone.
A mode that starts from `enriched/` and runs the image enricher alone costs one vision
call per image and touches only the two image fields.

### AD-3: Invalidation lives in `index quiz`, as its own step, ordered before the store

Enforcing it at the write point makes "no labeling is ever based on a superseded
description" an invariant, whatever way a description changes, instead of a manual
follow-up command someone must remember. A separate step keeps `StoreQuizStep` at its
current three tables. Ordering before the store makes the failure direction safe: if the
store then fails, the only effect is deleted labelings that get recomputed on demand.
Precedent for the ingestor writing labeling tables: `ingest reset knowledge` already
truncates `quiz_labelings`/`quiz_comma_labels`.

## Data Model

No schema change. `quiz_images.description`, `quiz_labelings.validated_at` and the
`quiz_comma_labels → quiz_labelings` relationship are used as they exist.

## Package Structure

```
configs/agents/road_sign_describer.yaml                         # FR-2, FR-3
src/guidami_ai_patente_ingestor/
├── agents/dto/road_sign_describer/road_sign_describer_request.py  # FR-1 (statement model)
├── agents/mappers/road_sign_describer_mapper.py                   # FR-1
├── orchestrators/quiz_flows.py              # FR-4 new factory; FR-5 step wired in
├── orchestrators/steps/quiz/invalidate_stale_labelings_step.py    # FR-5 (new)
├── repositories/…                           # FR-5 read of current descriptions + delete
└── cli/commands/prepare.py                  # FR-4 flags, dry-run rendering
```

One class per file; the new labeled-statement DTO gets its own file in the same `dto/`
package, re-exported from its `__init__.py`.

## Constraints

- Follows `.claude/rules/` (no `continue`, lazy logging args, one class per file,
  dependency-last constructor args, `UseCase` invocation via `__call__`).
- Ingestor keeps manual constructor injection (not pywire).
- Response DTO docstrings/`Field(description=...)` stay Italian (prompt-facing); request
  DTOs stay English.

## Testing

TDD for production code:

- Mapper: correct answers reach the contexts; deduplication behaviour unchanged;
  `contexts_block` renders `(Vero)`/`(Falso)`.
- Regeneration flow (FR-4): rewrites only `image_description`/`image_analysis`; respects
  `--image`; unknown `--image` is a usage error; `--only` with `--force` is a usage
  error; a failed image keeps its old description; `--dry-run` writes nothing.
- `InvalidateStaleLabelingsStep` (`@pytest.mark.integration`, test Postgres stack):
  deletes only labelings of questions whose image description changed; spares validated
  ones; no-op when nothing changed; handles a previously-missing description.

Prompt quality is validated manually, not by tests: run FR-4 with `--image` on ~10 known
hard images (21137, 20568, …), review the descriptions, then run on all images.

## Rollout

1. Implement FR-1…FR-5.
2. `uv run ingest prepare quiz --only image-descriptions --image …` on the sample; review.
3. `uv run ingest prepare quiz --only image-descriptions` on all 427 images (~5 $ at
   current OpenRouter prices).
4. `uv run ingest index quiz` — re-embeds, updates `quiz_images`, invalidates stale
   labelings (FR-5).
5. Commit the changed `data/enriched/` files.

## Feasibility Evidence

- `ImageDescriptionEnricherService` (`services/quiz/enrichers/image_description_enricher.py`)
  already groups by image over whatever list it is given and degrades per image — reusable
  unchanged for FR-4.
- `RoadSignDescriberMapper.from_response_to_enriched_quiz` only sets `image_description`
  and `image_analysis`.
- `EnrichedQuizModel.correct_answer: bool` is available at mapping time.
- `build_quiz_enrichment_flow` shows the load/map/enrich/write step shapes FR-4 reuses;
  `build_quiz_indexing_flow` exposes `QUIZ_IMAGE_ENTITIES` before `StoreQuizStep`.
- DB on 2026-09-27: 85 labelings, 41 on image questions, 0 validated.
- OpenRouter pricing on 2026-09-27: `google/gemini-3.8-flash` 0.75 $/M input, 3.75 $/M
  output.

## Open Questions

- [ ] **non-blocking** — Exact describer prompt wording; tuned on the sample run.

## Follow-ups after implementation

- `second-brain:adr`: new ADR superseding ADR 0001 (AD-1).
- `second-brain:update`: `architecture.md` (describer input, regeneration mode, index-side
  invalidation), `patterns.md` if the invalidation step is a reusable pattern.
- `CLAUDE.md` scripts table: document `prepare quiz --only image-descriptions`.
- Update the user memory note on the answer-blind describer.

## Sign-off

- **Scope approved by user:** design approved in chat, 2026-09-27; written spec pending
  review.
- **Feasibility asserted:** by the assistant on 2026-09-27, per Feasibility Evidence.
- **Definition of Done verified:** not yet.

## Changelog

- **2026-09-27** — Initial draft from the brainstorming session.
