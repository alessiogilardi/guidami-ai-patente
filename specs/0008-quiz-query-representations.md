# Spec 0008: Quiz Query Representations

| | |
|---|---|
| **Id** | 0008 |
| **Status** | draft |
| **Date** | 2026-08-05 |
| **Discussion log** | none — compiled directly from conversation |
| **Supersedes / superseded by** | — |

## Problem & Motivation

Every quiz question in the database carries exactly one vector, and that vector is
computed from a single choice nobody has ever tested: the LLM-generated
`vector_search_queries`, joined into one string. The question's own text and its topic —
the only fields written by a human rather than a model — take no part in retrieval at all.
Whether that is the right choice is unknown, because there has never been an alternative to
compare it against.

The choice is also currently unauditable. `vector_search_queries` is used to compute the
embedding and then discarded: the quiz mapper drops it on the way to the entity, and no
column holds it. Given a question that retrieves badly, there is no way to see the text
that produced its query vector — the single most useful piece of evidence for diagnosing
the failure. The other three metadata fields were promoted to first-class columns by
ADR 0002 precisely so they would be inspectable; this one was left behind. The same is
true of the vision-generated image descriptions: 4147 of the 7099 questions carry an
image, the description of what that image depicts is generated during enrichment, and it
is then thrown away at the storage boundary — so for well over half the bank, the most
semantically loaded text about the question never reaches the database at all.

Spec 0007 establishes the instrument that makes the comparison possible and captures a
baseline of the current single-representation configuration. This spec uses that
instrument to answer the question the baseline poses: which representation of a quiz
question retrieves its supporting norm best?

## Functional Requirements

### FR-1: Persist `vector_search_queries`

The phrases that produce a question's query vector are stored on the quiz row.

**Acceptance criteria:**
- Given an enriched quiz item with `quiz_metadata`, when it is stored, then its
  `vector_search_queries` are persisted as a `TEXT[]` column on `quiz_questions`.
- Given an item whose `quiz_metadata` is `None`, when it is stored, then the column is
  `NULL`, consistent with the other three metadata columns.
- Given a stored row, when it is read back, then the persisted phrases are identical to
  those in the enriched layer file for that question.

### FR-2: Query representations stored as variants, not as columns

A quiz question carries any number of independently computed vectors, each identified by
the representation that produced it.

**Acceptance criteria:**
- Given a quiz item, when indexing runs, then each configured representation produces one
  row in a variant table keyed by question and variant name — adding a representation
  never requires a schema change.
- Given the initial configuration, when indexing runs, then it produces at least these
  variants: question text alone; topic + question text; `vector_search_queries`; topic +
  text + `vector_search_queries` combined.
- Given the `vector_search_queries` variant, when it is computed, then it reproduces the
  representation measured by the spec 0007 baseline exactly, so the baseline stays
  comparable.
- Given an item lacking the input a representation needs, when indexing runs, then no row
  is written for that variant and the omission is counted, never stored as a null vector.
- Given a variant name, when it is written, then it states the text it was computed from;
  no variant is called `embedding`.

### FR-3: The harness evaluates every stored variant, plus fusion

The 0007 harness enumerates the variants present in the database and compares them, plus a
fusion arm that requires no additional storage.

**Acceptance criteria:**
- Given a completed evaluation run, when results are reported, then every metric defined
  in spec 0007 is reported per arm, where an arm is a (variant, embedding model) pair, with
  both the variant list and the populated model columns read from the database rather than
  hardcoded in the harness.
- Given only one embedding model is populated, when results are reported, then the model
  axis collapses silently and arms are labelled by variant alone — a second model must not
  be required for the harness to run.
- Given the fusion arm, when it is computed, then a question's variants query the corpus
  independently and the resulting rankings are fused by Reciprocal Rank Fusion — no fused
  vector is stored.
- Given a completed run, when results are reported, then the `search_queries` variant is
  identified as the baseline arm and every other arm's delta against it is shown.
- Given a question missing a variant, when arms are computed, then it is excluded from the
  arms it cannot support, and the excluded count is reported per arm rather than silently
  absorbed.
- Given the image-description arm, when it is reported, then its metrics are computed only
  over questions that have an image, and never compared directly against arms measured on
  a different population.

### FR-4: Re-ingestion without re-enrichment

Rebuilding the database for the new schema costs embeddings only.

**Acceptance criteria:**
- Given the enriched layer on disk, when the quiz index command is re-run after the
  schema change, then no LLM enrichment call is made.
- Given a completed re-ingestion, when `llm_call_logs` is inspected, then it contains no
  new enrichment rows attributable to the run.
- Given a completed re-ingestion, when the quiz table is inspected, then the number of
  rows matches the number of enriched layer files.

### FR-5: Image descriptions stored once per image

The vision-generated description of a road sign is persisted once per image and made
available as a query representation.

**Acceptance criteria:**
- Given an enriched quiz item with an image description, when it is stored, then the
  description is written to a table keyed by image filename, not duplicated onto every
  question referencing that image.
- Given several questions sharing one image, when their descriptions are stored, then the
  table holds exactly one row for that image.
- Given a question with an image, when indexing runs, then a variant is produced from its
  image description, so image questions can be retrieved through what the sign depicts
  rather than only through the question text.
- Given a question with no image, when indexing runs, then no image-description variant is
  produced for it.

## Non-Goals

- **Changing the corpus-side representation** — `article_commas` continues to embed
  article title + comma text. This spec varies the query side only; varying both at once
  would make the results uninterpretable. The variant-table pattern in AD-2 applies
  equally to the corpus side and makes that experiment cheap to run later, once the query
  side has a winner to hold fixed.
- **Implementing hybrid search** — the fusion arm in FR-3 fuses three dense rankings as a
  measurement. Fusing dense with full-text search remains a separate, still-unfunded
  decision that spec 0007's measurements inform.
- **Choosing the winning representation** — this spec produces the comparison. Promoting
  one arm to the production default is a decision taken after reading the numbers, and
  will amend this spec or open a new one.
- **Expanding the corpus** — the missing-source work (first aid, vehicle mechanics) is
  spec 0009 and requires its own discovery.
- **Re-running LLM enrichment** — the enriched layer is versioned and complete; nothing
  here regenerates it.

## Architectural Decisions

### AD-1: `vector_search_queries` becomes a column, completing ADR 0002
- **Rationale:** ADR 0002 flattened the metadata blob into first-class columns so each
  field's role would be visible and queryable. `vector_search_queries` was excluded because
  at the time it was only embedder input. It is now also the thing under test, and a
  representation that cannot be inspected cannot be debugged. Making it a `TEXT[]` column
  matches the shape and nullability already established for `core_concepts` and
  `exact_keywords`.
- **Rejected alternatives:** Keeping it transient and reading the enriched JSON when
  needed — splits the evidence for one question across a database row and a file on disk,
  and breaks entirely once the enriched layer is regenerated.

### AD-2: Representations are rows in a variant table, not columns on `quiz_questions`
- **Rationale:** What to embed is an open question, not a settled one — the arms listed in
  FR-2 are the current guesses, and the image-description arm was added while this spec was
  being written. Encoding each representation as a column makes every new idea cost a
  schema edit, a database wipe and a full re-ingest, which in practice means ideas do not
  get tested. A `(quiz_question_id, variant, embedding)` table turns adding a
  representation into an ingest run, and turns "which arms exist" into data the harness can
  enumerate instead of a list hardcoded in three places. The cost is one join per query,
  which is irrelevant against an exact scan of 3650 commas.
- **Rejected alternatives:** Three named vector columns (this spec's original decision) —
  cheaper to query, but freezes the arm set into the schema exactly when the arm set is
  the thing under investigation, and would have needed a second reset the moment the image
  arm appeared. Keeping the single `embedding` column and adding two — same defect, plus
  it preserves a name that stops meaning anything once variants exist.

### AD-3: The fourth arm is fusion at query time, not a fourth stored vector
- **Rationale:** Concatenating three texts into one embedding averages three distinct
  semantic contents into a single point, which frequently retrieves worse than its best
  component; the combined arm in FR-2 tests exactly that risk. Querying with the three
  vectors separately and fusing the rankings preserves each representation's precision and
  costs nothing extra, since all three vectors are stored regardless. It also exercises the
  fusion mechanics that a later hybrid-search decision would reuse.
- **Rejected alternatives:** A fourth stored vector — no representation left to compute
  that the other three do not already cover. Omitting the fusion arm — it is the cheapest
  arm to add and the most likely to win.

### AD-4: The schema change is applied by an idempotent migration script, not a reset
- **Rationale:** A reset would discard every vector in the database and force the whole
  corpus to be re-embedded, including the 3650 comma vectors this spec does not touch.
  Worse, it would destroy the spec 0007 baseline in place, which is why an ordering
  constraint was needed to capture it first. A migration avoids both: `article_commas` is
  untouched, and the existing `quiz_questions.embedding` values are moved into the variant
  table as the `search_queries` variant before the column is dropped — so the baseline arm
  survives verbatim and never needs recomputing. The ordering constraint dissolves with it.
- **Rejected alternatives:** Wipe the bind mount and re-ingest (this spec's original
  decision) — throws away recoverable-but-paid-for work and makes the baseline fragile.
- **Mitigation of the risk this introduces:** without a migration tool, a migration script
  is a second schema-management mechanism running in parallel with `db/init.sql`, and the
  two can silently drift — a freshly created volume would then differ from a migrated
  database. Both files are therefore written and reviewed as one change, and the migration
  ships with an `information_schema` equivalence check to be run against both a migrated
  and a freshly initialised database.

### AD-5: Image descriptions live in their own table, keyed by filename
- **Rationale:** ADR 0003 already established that a description belongs to an image, not
  to a question: the enricher makes exactly one vision call per distinct image. The data
  confirms the cardinality — 4147 questions reference 427 images, so a column on
  `quiz_questions` would store each description roughly ten times and admit the possibility
  of ten divergent copies, which is precisely what ADR 0003 set out to prevent. A table
  keyed by filename makes that impossible by construction.
- **Rejected alternatives:** A nullable `image_description` column on `quiz_questions` —
  simpler to write, but denormalises a 1:N relationship and reintroduces the divergence
  ADR 0003 removed. Leaving descriptions unpersisted as today — makes the image arm in
  FR-5 impossible and keeps the most informative text for image questions out of reach.

### AD-6: The embedding model is a column axis, orthogonal to the variant row axis
- **Rationale:** pgvector encodes the dimension in the column type, so vectors from models
  of different dimensionality cannot share a column — `text-embedding-3-small` (1536) and
  `text-embedding-3-large` (3072) are physically incompatible values. Model choice is
  therefore expressed as one column per model, while the representation stays a row. The
  two axes are independent: any variant can be embedded by any model, and the table
  supports the full matrix without further schema work beyond one `ADD COLUMN` per new
  model. This also keeps a model comparison from being conflated with a representation
  comparison, which sharing a column would force.
- **Rejected alternatives:** A `model TEXT` key column with a single `embedding` column —
  requires every model to share one dimension, which is false for the obvious candidates.
  A table per model — duplicates the variant structure and the foreign key for no gain.
  Storing the largest dimension and truncating — silently degrades models that are not
  Matryoshka-trained.
- **Consequence:** the per-column `NOT NULL` that enforced "no empty vectors" cannot
  survive multiple model columns, since a row may legitimately hold one model's vector and
  not another's. The invariant moves to a table-level `CHECK (num_nonnulls(...) > 0)`,
  which must be widened in the same transaction that adds a model column.

## Data Model

**`quiz_questions`** — gains `vector_search_queries TEXT[]` (nullable, alongside
`core_concepts` and `exact_keywords`); loses `embedding VECTOR(1536)`, which moves to the
variant table below.

**`quiz_question_embeddings`** (new) — one row per question per representation:

| Column | Notes |
|---|---|
| `quiz_question_id BIGINT` | FK to `quiz_questions(id)`, `ON DELETE CASCADE` |
| `variant TEXT` | names the text embedded, e.g. `text`, `topic_text`, `search_queries`, `combined`, `image_description` |
| `embedding_3_small VECTOR(1536)` | nullable — one column per embedding model; a second model gets its own column |
| | `UNIQUE (quiz_question_id, variant)`, index on `variant` |
| | `CHECK (num_nonnulls(embedding_3_small) > 0)` — widened whenever a model column is added |

Two orthogonal axes: **which text** was embedded is a row (`variant`), **which model**
produced the vector is a column. A representation that was never computed is an absent
row; a model that has not been run for an existing representation is a `NULL` column.

**`quiz_images`** (new) — one row per distinct image, not per question:

| Column | Notes |
|---|---|
| `filename TEXT PRIMARY KEY` | matches `quiz_questions.image_filename` |
| `description TEXT` | the vision-generated description, produced once per image per ADR 0003 |

Measured on the current database: 4147 questions reference only 427 distinct images, so a
description column on `quiz_questions` would store each description about ten times.

Storage impact is negligible: five variants for ~7100 questions is roughly 200 MB. No
vector index is added, consistent with the exact-scan decision in spec 0007.

`article_commas` and `articles` are untouched in shape, but both are re-populated by the
reset.

Migration: apply `db/migrations/0008_quiz_query_representations.sql` to the running
database, then re-run quiz indexing to populate `vector_search_queries`, `quiz_images`,
and every variant other than `search_queries`. `db/init.sql` is updated in the same change
to the identical target state, for freshly created volumes. Knowledge indexing does not
need to be re-run: `articles` and `article_commas` are untouched.

## Constraints

- The migration must preserve `quiz_questions.embedding` as the `search_queries` variant
  **before** dropping the column. Dropping it first destroys the spec 0007 baseline arm,
  which is the one thing in this change that cannot be recomputed for free.
- `article_commas` and `articles` must come through the migration untouched; a run that
  re-embeds the corpus has done something wrong.
- The migration must be idempotent and transactional: re-running it is a no-op, and a
  failure leaves the schema unchanged rather than half-applied.
- `db/init.sql` and the migration must produce identical schemas, verified by the
  equivalence check rather than assumed.
- Vector parameters use the explicit `%s::vector` cast, per
  `.claude/rules/code-conventions.md`.
- Entities model the insertable projection of the row: the three vector fields are plain
  nullable fields, and DB-generated columns stay absent, per the same rules file.
- Re-embedding cost must stay within a few cents: roughly 25 000 items across quiz arms
  and corpus commas at `text-embedding-3-small` rates.
- No new runtime dependency.

## Feasibility Evidence

- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py:54` — the mapper docstring states it drops `vector_search_queries` as "embedder input only, not persisted", the exact behaviour FR-1 reverses (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `docs/adr/0002-flatten-quiz-metadata-columns.md:10` — lists `vector_search_queries` among the metadata fields, establishing the flattening precedent this extends (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `db/init.sql:41` — `core_concepts TEXT[]` shows the column shape and nullability the new column follows (verified 2026-08-05 @ 6d96b7d)
- **AD-2** — supported by: `db/init.sql:44` — the single `embedding VECTOR(1536)` column this decision replaces (verified 2026-08-05 @ 6d96b7d)
- **AD-2** — supported by: `src/domain/entities/quiz/quiz_question.py:22` — the entity's single `embedding: list[float] | None` field that must become three (verified 2026-08-05 @ 6d96b7d)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/embedded_quiz.py:21` — the intermediate model's single `embedding` field, the second place the three-way split lands (verified 2026-08-05 @ 6d96b7d)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py:24` — `embedded_text` joins `vector_search_queries`, the single representation all four arms are measured against (verified 2026-08-05 @ 6d96b7d)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/services/quiz/embed_quiz_metadata.py:11` — `EmbedQuizMetadata` computes exactly one vector per item, the step FR-2 generalises (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `src/commons/ai/embedding/configs/embedding_config.py:17` — the comment states `dimensions` "must match `vector_dim` and the `VECTOR(N)` column size", confirming dimension is fixed per column and cannot vary per row (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `db/init.sql:69` — the table-level `CHECK (num_nonnulls(...) > 0)` that replaces the per-column `NOT NULL` once multiple model columns are possible (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `db/migrations/0008_quiz_query_representations.sql:65` — the guarded `INSERT ... SELECT` that moves existing vectors into the variant table before the column is dropped (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `db/init.sql:52` — the target-state definition the migration must match, updated in the same change (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `docs/adr/0003-group-road-sign-description-by-image.md:24` — "Group by the image filename only", establishing that a description belongs to an image rather than to a question (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py:52` — the mapper discards `image_description` as not persisted, the behaviour FR-5 reverses (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/embedded_quiz.py:20` — `image_description: str | None` exists on the intermediate model, so the text is already carried to the storage boundary and only needs a destination (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:75` — documents that the embedding comes from `vector_search_queries` rather than the quiz text, confirming the indexing flow is the single place to extend (verified 2026-08-05 @ 6d96b7d)

## Open Questions

- [ ] **non-blocking** — Quiz topics are long descriptive strings (one exceeds 300
  characters) and may dominate the vector they appear in. FR-2 now includes a topic-free
  `text` variant precisely so this can be measured rather than argued; if the topic proves
  harmful, the `topic_text` and `combined` variants inherit the problem. — owner: investigation
- [ ] **non-blocking** — Should the image-description variant also be produced for the
  ~2950 questions with no image, by falling back to the question text? Doing so keeps the
  arm's population uniform; not doing so keeps the arm honest. FR-3 currently chooses the
  latter. — owner: user
- [ ] **non-blocking** — Which RRF constant `k` should the fusion arm use? The
  conventional default is 60; it has never been calibrated on this corpus. — owner: investigation
- [ ] **non-blocking** — After the winning arm is chosen, do the losing columns stay in the
  schema as permanent experiment scaffolding, or are they dropped in a follow-up reset? —
  owner: user

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

- **2026-08-05** — AD-2 reversed before sign-off: representations are stored as rows in a
  `quiz_question_embeddings` variant table rather than as three named columns on
  `quiz_questions`. Prompted by the user's observation that what to embed is still an open
  question — a column-per-arm schema makes every new idea cost a database wipe, which the
  image-description arm demonstrated immediately by appearing mid-draft. FR-2 and FR-3 were
  rewritten accordingly, with the harness enumerating variants from the database instead of
  a hardcoded list, and a topic-free `text` variant added.
- **2026-08-05** — New FR-5 and AD-5 persist vision-generated image descriptions in a
  `quiz_images` table keyed by filename, and add an image-description query variant.
  Measured cardinality drove the shape: 4147 questions reference only 427 distinct images,
  so a column on `quiz_questions` would duplicate each description about ten times and
  reintroduce exactly the divergence ADR 0003 eliminated.
- **2026-08-05** — AD-4 reversed on user request: the schema change is applied by an
  idempotent, transactional migration (`db/migrations/0008_quiz_query_representations.sql`)
  instead of wiping the volume and re-ingesting. This preserves the 3650 corpus vectors
  untouched and migrates the 7098 existing quiz vectors into the variant table as
  `search_queries`, so the spec 0007 baseline arm survives verbatim. Consequences: the
  constraint requiring a committed 0007 baseline before the schema change **dissolves** —
  the baseline is no longer destroyed by the change — and spec 0007's corresponding
  constraint was relaxed to match. The risk this introduces (two parallel schema
  mechanisms drifting) is mitigated by updating `db/init.sql` to the identical target
  state in the same change and shipping an `information_schema` equivalence check.
- **2026-08-05** — On user request, `quiz_question_embeddings` is provisioned for more than
  one embedding column. New AD-6 makes the embedding model a column axis orthogonal to the
  variant row axis, because pgvector fixes the dimension in the column type and models of
  different dimensionality cannot share a column. The single column is renamed from
  `embedding` to `embedding_3_small` so a second model can join it without a rename, and
  the per-column `NOT NULL` becomes a table-level
  `CHECK (num_nonnulls(...) > 0)` — the "no empty vectors" invariant cannot be expressed
  per column once a row may legitimately hold one model's vector and not another's. FR-3
  now defines an arm as a (variant, model) pair while keeping single-model runs valid. The
  migration carries a commented template for adding a model column together with the
  required CHECK widening.
