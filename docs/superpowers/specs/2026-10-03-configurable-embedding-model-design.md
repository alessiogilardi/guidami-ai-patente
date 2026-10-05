<!--
SPEC — the contract. Durable, git-tracked, never deleted (superseded instead).
The user signs scope; the compiling skill asserts feasibility with codebase evidence.
Downstream plans are extracted from this document and reference FR ids: every
requirement must be individually testable and traceable.
Status lifecycle: draft → ready → in-progress → implemented → superseded.
Every status beyond draft is written by the user alone — skills only propose.
-->

# Spec 0026: Configurable embedding model (step 1 of the move to text-embedding-3-large)

| | |
|---|---|
| **Id** | 0026 |
| **Status** | draft |
| **Date** | 2026-10-03 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`; no transcript file) |
| **Supersedes / superseded by** | Reverses the "deliberately a constant" decision documented in `src/labeling/constants.py` (spec 0012 D7) |

## Problem & Motivation

The project embeds with `text-embedding-3-small` (1536 dimensions). Moving to
`text-embedding-3-large` (3072 dimensions) is wanted, but the embedding model is wired in
as a fact of the code instead of a setting:

- `labeling/constants.py::EMBEDDING_MODEL_COLUMN = "embedding_3_small"` is imported by the
  batch labeler and by two API services; `RetrievalJudgeEvaluationService` hardcodes the
  same literal; `QuizQuestionRepository.find_question_vocabulary_context` hardcodes
  `e.embedding_3_small` in SQL.
- The corpus side is **not** model-versioned at all: `article_commas.embedding` is a single
  unversioned `VECTOR(1536)` column, hardcoded in `CorpusReadRepository.dense_top_k`,
  `random_top_k` and `keyword_document_frequency`. The dense arm compares a quiz vector with
  a comma vector, so both sides must come from the same model: a model switch is a switch of
  **both** columns, never of the quiz column alone.
- The ingestion writers hardcode their column names (`QuizQuestionEmbeddingEntity.embedding_3_small`,
  `_ARTICLE_COMMA_TABLE_COLUMNS`), and the embedder's model is a second, independent setting
  (`IngestorConfig.embedding.model_name`).
- The model is not part of the labeling configuration epoch. The constant's docstring says
  why it stayed a constant: making it configurable obliges it to enter the epoch, otherwise a
  switch would serve labelings judged on another model's vectors under an identical cache
  key (the failure AD-8 of spec 0012 exists to prevent).

This spec is **step 1**: make the model a single configuration value that selects, in one
place, the embedder, the vector column of every table and the epoch. It changes **no
behaviour**: the only registered model is `text-embedding-3-small`. Step 2 (a later spec)
then adds `embedding_3_large` columns, re-embeds, compares and switches — as additive schema
plus one changed config value.

## Functional Requirements

### FR-1: A closed registry of embedding models

- `EmbeddingModel` — a `StrEnum` in `src/domain/enums/embedding_model.py`, one member today:
  `TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"`. The value is written explicitly
  rather than with `auto()` because it is an external contract (persisted in
  `labeling_runs.embedding_model` and written in `labeling.yaml`), with an inline comment
  saying so (`.claude/rules/code-conventions.md`).
- `EmbeddingModelSpec` — a frozen Pydantic model in `commons/ai/embedding/models/` with
  `model_name` (the litellm id, e.g. `openrouter/openai/text-embedding-3-small`), `column`
  (the `embedding_*` column name used by **every** table, e.g. `embedding_3_small`) and
  `dimensions` (1536).
- `EMBEDDING_MODEL_REGISTRY: Mapping[EmbeddingModel, EmbeddingModelSpec]` next to it, with
  one entry. A test asserts the registry has an entry for every enum member.

### FR-2: One configuration key selects the model

`LabelingConfig` (`configs/labeling.yaml`, read by both `IngestorConfig` and `AppConfig`)
gains `embedding_model: EmbeddingModel = EmbeddingModel.TEXT_EMBEDDING_3_SMALL`, added to
`EPOCH_FIELDS`, and a derived read-only property `embedding_spec` returning the registry
entry. An unknown value is a `ValidationError` at startup. `configs/labeling.yaml` gets the
key with its default, so the choice is visible in the file.

### FR-3: The model is the seventh field of the configuration epoch

- `LabelingEpoch` gains `embedding_model: str` (a plain string, like `judge_model`; the enum
  exists only at the config boundary). `LabelingEpochMapper` fills it from `LabelingConfig`.
- `LabelingRunEntity`, `LabelingRunMapper`, `GoldenSetWriteRepository` (`_RUN_COLUMNS`,
  `find_or_create_live_run`'s lookup) and `GoldenSetReadRepository.find_current_labeling`
  (precedence query) carry the field.
- `labeling_runs.embedding_model TEXT NOT NULL` and `uq_labeling_runs_live_config` gains it
  as a seventh key column.
- Precedence is unchanged: a human-validated labeling still qualifies whatever run produced
  it; a non-validated labeling qualifies only under the current epoch. Consequence: changing
  `embedding_model` makes every non-validated labeling non-current **without a `DELETE`**,
  and validated ones keep serving.
- `LabelingEpoch`'s docstring ("the six inputs") and `LabelingConfig`'s are updated.

### FR-4: Schema migration, additive for data, with the corpus column renamed

`db/migrations/0026_configurable_embedding_model.sql` (and the same edit in `db/init.sql`):

1. `labeling_runs` — `ADD COLUMN IF NOT EXISTS embedding_model TEXT`; backfill
   `UPDATE … SET embedding_model = 'text-embedding-3-small' WHERE embedding_model IS NULL`;
   `SET NOT NULL`. Existing runs keep their identity: they were computed with that model.
2. `uq_labeling_runs_live_config` — `DROP INDEX IF EXISTS` then recreate with the seventh
   column, same `WHERE origin = 'live'`.
3. `article_commas.embedding` → `embedding_3_small`, inside a `DO $$` block that renames only
   if `embedding` exists and `embedding_3_small` does not (`RENAME COLUMN` has no
   `IF EXISTS` form). Metadata-only: no rewrite, the `VECTOR(1536)` type and data are
   untouched.

Idempotent, one transaction, with a manual rollback section, named after the spec, as
`db/migrations/0022_*.sql`. Applied to the dev stack through path 2 of CLAUDE.md, with
row counts of `article_commas` and `labeling_runs` checked before and after.

### FR-5: The corpus repository takes its vector column as a parameter

`CorpusReadRepository.__init__(articles_table, article_commas_table, embedding_column, client)`
(plain data before the dependency). `dense_top_k`, `random_top_k` and
`keyword_document_frequency` interpolate it as `sql.Identifier` in place of the literal
`c.embedding`. `labeling/wiring.py::build_corpus_repository` and
`cli/wiring.py::build_evaluation_repositories` pass `config.labeling.embedding_spec.column`.
`comma_count` and the text-arm methods are untouched.

### FR-6: Every reader of a quiz vector takes the column from configuration

`EMBEDDING_MODEL_COLUMN` and `labeling/constants.py` are deleted. The former consumers read
`embedding_spec.column` from `LabelingConfig`:

- `CommaSelectorService` and `ExplanationService` (pywire, `labeling_config: Autowired[LabelingConfig]`);
- `GoldenSetLabelingService` and `RetrievalJudgeEvaluationService` (a new `embedding_column`
  constructor argument, replacing the constant and the `"embedding_3_small"` literal);
- `QuizQuestionRepository.find_question_vocabulary_context` (the SQL `e.embedding_3_small`
  becomes `e.{column}`); `has_embedding`'s docstring about the single-column CHECK is
  updated to point at the registry.

### FR-7: Ingestion writes the configured column and embeds with the configured model

- `QuizQuestionEmbeddingEntity.embedding_3_small` is renamed `embedding` (the physical
  column is chosen by the repository — precedent: `GlossaryEntryEntity.embedding`).
  `QuizQuestionEmbeddingStoreRepository` and `ArticleCommaStoreRepository` take
  `embedding_column` and put it in their `columns` tuple at the position of the vector;
  `ArticleCommaEntity.embedding` is unchanged. `StoreQuizStep` and the mappers follow.
- `IngestorConfig.embedding` stops carrying the model: `model_name` and `vector_dim` leave
  `configs/ingestor_config.yaml`; the client config handed to `LiteLLMEmbeddingClient`
  (`cli/commands/index.py`) is built from `labeling.embedding_spec` plus the remaining
  `timeout`/`num_retries`. `EmbeddingClientConfig.vector_dim` is derived from the spec so it
  cannot disagree with the column.

### FR-8: The glossary's read side follows the same model

`GlossaryReadRepository` reads `labeling_config.embedding_spec.column` instead of
`AppConfig.glossary.embedding_column`, which is removed (`GlossaryRetrievalConfig`,
`configs/app_config.yaml`). The dense arm compares a quiz vector (the `text` variant, see
Open Questions) with `glossary_entries.<column>`; both must always be the same model.

### FR-9: No behaviour change

With the default configuration:

- every SQL statement is unchanged except the corpus column name;
- every existing labeling that is current before the migration is current after it;
- `uv run ingest evaluate retrieval` produces a `data/eval/retrieval-summary.json`
  identical to the committed one;
- the unit and integration suites pass.

## Non-Goals

- No `embedding_3_large` column, no re-embedding, no switch, no A/B comparison (step 2).
- No change to `GlossaryConfig.embedding_column` or to `glossary/wiring.py`, which builds the
  glossary embedder from `EmbeddingClientConfig()` defaults: the build side is a separate
  settings root without `LabelingConfig`. It is a prerequisite of step 2, not of this spec.
- No change to the CHECK `num_nonnulls(embedding_3_small) > 0` (still one model column).
- No generalisation of `MultiArmRetrievalEvaluator` to compare several models (it reads the
  quiz table's populated columns but queries one corpus column): step 2.
- No new embedding variants, no vector index, no batch relabel.

## Architectural Decisions

### AD-1: The model enters the epoch (reverses spec 0012 D7)

Making the column configurable without the epoch would let a config change serve labelings
judged on other vectors under an unchanged cache key. Alternatives: keep a constant and add
a manual "delete non-validated labelings" script (rejected: relies on being run, failure is
silent); keep the constant. Chosen: the field, so a switch is structural and rollback
(setting the key back) re-activates the old epoch's labelings. Cost: one migration on
`labeling_runs` and the unique index.

### AD-2: One key drives every table's column

The registry gives one `column` per model and every table (`quiz_question_embeddings`,
`article_commas`, `glossary_entries`) uses that name. Independent per-table keys were
rejected: two models of equal dimension would be compared silently, while models of
different dimension would fail only at query time. A single key makes the mismatch
unrepresentable.

### AD-3: Rename `article_commas.embedding` instead of mapping around it

Alternative: a second registry field `corpus_column` mapping small to `embedding`. Rejected:
the asymmetry would stay forever and step 2 would add `embedding_3_large` beside a column
called `embedding`. The rename is metadata-only. Trade-off: a window where code and schema
disagree — running API and ingestion processes must be restarted with the migration.

### AD-4: Backfill existing runs to `text-embedding-3-small`

They were computed with it, and the default config names it: their labelings stay current.
Alternatives: leave the column nullable (the epoch key would need `IS NOT DISTINCT FROM`
everywhere); open a new epoch (needless invalidation of a golden set that is still valid).

### AD-5: Persistence entities stay generic; repositories own the physical column

`embedding` on the entity, the column name injected into the store repository — the shape
`GlossaryEntryEntity` already uses. Keeps the entity free of a model name that changes.

### AD-6: Clean-architecture check (`clean-architecture`, 2026-10-03)

Dependency Rule: `domain/enums` (`EmbeddingModel`) ← `commons/ai/embedding` (spec, registry)
← `labeling/configs` (selection) ← `IngestorConfig`/`AppConfig`; repositories and services
receive a plain `embedding_column: str`, never a config object, so `commons/repositories/db`
does not import `labeling`. SRP: the registry changes when a model is added; the config when
the choice changes; repositories when a query changes. The column is always an enum-derived
`sql.Identifier`, never user input. Deliberate deviation: `LabelingConfig`, described as the
judge's identity, now also names the embedding model — accepted because it is the single
file both roots read (AD-27) and the model is epoch-bearing. Project conventions respected:
dependency-last constructor order, `StrEnum` in `enums/`, one class per file, pywire field
injection in `guidami_ai_patente`, manual injection elsewhere.

## Data Model

See FR-4. Resulting `labeling_runs` key (live):
`(judge_model, prompt_version, candidate_variant, dense_k, text_k, lexeme_fields, embedding_model)`.
`article_commas.embedding_3_small VECTOR(1536)` replaces `embedding`; no other column
changes.

## Package Structure

```
db/init.sql, db/migrations/0026_configurable_embedding_model.sql
configs/labeling.yaml                                   # embedding_model key
configs/ingestor_config.yaml                            # drops embedding.model_name / vector_dim
configs/app_config.yaml                                 # drops glossary.embedding_column
src/domain/enums/embedding_model.py                     # FR-1 (new)
src/domain/entities/quiz/quiz_question_embedding.py     # FR-7 field rename
src/commons/ai/embedding/models/embedding_model_spec.py # FR-1 (new)
src/commons/ai/embedding/models/embedding_model_registry.py   # FR-1 (new)
src/commons/repositories/db/corpus_read_repository.py   # FR-5
src/labeling/{constants.py (deleted), configs/labeling_config.py, models/labeling_epoch.py,
  mappers/{labeling_epoch,labeling_run}_mapper.py, repositories/golden_set_write_repository.py,
  services/golden_set_labeling_service.py, wiring.py}   # FR-2, FR-3, FR-5, FR-6
src/domain/entities/evaluation/labeling_run.py          # FR-3
src/guidami_ai_patente/{repositories/{golden_set_read,quiz_question,glossary_read}_repository.py,
  services/{comma_selector,explanation}_service.py, configs/glossary_retrieval_config.py}  # FR-3, FR-6, FR-8
src/guidami_ai_patente_ingestor/{repositories/db/{quiz_question_embedding,article_comma}_store_repository.py,
  orchestrators/{knowledge_flows,quiz_flows}.py, orchestrators/steps/quiz/store_quiz_step.py,
  cli/{wiring.py,commands/index.py}, configs/ingestor_config.py}   # FR-5, FR-7
src/retrieval_evaluation/services/retrieval_judge_evaluation_service.py   # FR-6
```

Each new class in its own file, re-exported from its package `__init__.py`.

## Constraints

- Follows `.claude/rules/` (no `continue`, lazy logging args, English comments, one class per
  file, dependency-last constructor args, `UseCase` invocation via `__call__`).
- Refactor only: no new behaviour and no new model in this change.
- Migration through path 2 of CLAUDE.md; `db/init.sql` edited in the same change.
- Commits via `commit-moji`; a `second-brain:update` pass (database, architecture, patterns)
  and a new ADR are required before the branch is pushed.

## Testing

TDD for production code:

- Registry: an entry for every `EmbeddingModel`; `LabelingConfig` default, YAML override and
  rejection of an unknown model; `embedding_spec` matches the registry.
- Epoch: `LabelingEpochMapper` sets `embedding_model`; two configs differing only by it yield
  different epochs.
- `@pytest.mark.integration` (isolated test Postgres): the migration applies twice with no
  error and no change on the second run; the row count of `article_commas` and
  `labeling_runs` is unchanged and existing runs are backfilled; `article_commas` exposes
  `embedding_3_small` and no `embedding`; the live unique index has seven columns;
  `find_current_labeling` returns the same labeling before and after; a non-validated
  labeling under another `embedding_model` is not current while a validated one still is;
  `find_or_create_live_run` creates a distinct run per `embedding_model`.
- `CorpusReadRepository.dense_top_k` / `random_top_k` / `keyword_document_frequency` read the
  injected column (integration, two columns on a scratch table).
- Store repositories write the vector into the injected column; the embedder client config is
  derived from the spec.
- Regression: the existing suites (`uv run pytest`, `ruff`, `pyright`) stay green;
  `ingest evaluate retrieval` summary identical to the committed `data/eval/retrieval-summary.json`.

## Rollout

1. Implement FR-1…FR-8 on a branch.
2. Dev stack: record `SELECT count(*)` of `article_commas` and `labeling_runs`; apply the
   migration (path 2); re-check the counts.
3. Restart the API and any running ingestion with the new code (the rename breaks old code).
4. `uv run ingest evaluate retrieval` and diff the summary (FR-9); `uv run pytest`.
5. Second Brain: `second-brain:update` + ADR.

## Feasibility Evidence

- `CorpusReadRepository` builds its SQL with `psycopg.sql`; three methods name `c.embedding`.
- `QuizReadRepository` already takes `model_column` per call and discovers `embedding_*`
  columns from `information_schema`, so the quiz read side needs only its callers changed.
- `GlossaryEntryEntity.embedding` and `GlossaryConfig.embedding_column` are the existing
  precedent for a generic entity field plus a configurable physical column.
- The API never embeds a quiz at request time (`CommaSelectorService` docstring, AD-13):
  vectors come from `quiz_question_embeddings`, so no live embedder needs the registry.
- `LabelingConfig` is already read by `IngestorConfig` and `AppConfig`, which is what makes
  one key enough.

## Open Questions

- [ ] **non-blocking (step 2)** — The glossary dense arm uses the quiz **`text`** variant
  (`find_question_vocabulary_context`, `e.variant = 'text'`), not `topic_text`. Quiz
  retrieval for labeling uses only `topic_text` (`candidate_variant`), but the vocabulary
  stage still needs a `text` vector. Step 2 must either embed `text` with the new model too
  or move the glossary probe to `topic_text`.
- [ ] **non-blocking** — Spec 0025 (LLM provider decoupling, D6) also adds a field to the same
  epoch and unique index. Whichever lands second extends the other's migration; the
  migrations must be numbered and ordered accordingly.
- [ ] **non-blocking (step 2)** — `GlossaryConfig`/`glossary/wiring.py` (build side) must be
  tied to the same registry before the glossary can switch model.
- [ ] **non-blocking (step 2)** — Number of commas to re-embed (cost and time) is not yet
  measured; `MultiArmRetrievalEvaluator` needs a per-model corpus column to compare models.

## Follow-ups after implementation

- `second-brain:adr`: ADR "Embedding model is configuration and part of the epoch"
  (supersedes the constant decision in spec 0012 D7).
- `second-brain:update`: `database.md` (`labeling_runs.embedding_model`, `article_commas`
  column, unique index), `architecture.md` (registry, single key), `patterns.md`.
- CLAUDE.md: the epoch description lists the seventh field.
- Step 2 spec: `embedding_3_large` columns, re-embedding, A/B, switch.

## Sign-off

- **Scope approved by user:** design approved in chat, 2026-10-03; written spec pending review.
- **Feasibility asserted:** by the assistant on 2026-10-03, per Feasibility Evidence.
- **Definition of Done verified:** not yet.

## Changelog

- **2026-10-03** — Initial draft from the brainstorming session.
