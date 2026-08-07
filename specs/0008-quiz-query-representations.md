# Spec 0008: Quiz Query Representations

| | |
|---|---|
| **Id** | 0008 |
| **Status** | implemented |
| **Date** | 2026-08-06 |
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

Spec 0007 builds the instrument that makes the comparison possible. This spec uses it to
answer the question that instrument poses: which representation of a quiz question
retrieves its supporting norm best? The current single-representation configuration is
preserved as the `search_queries` variant by the migration (AD-4), so it remains
measurable whether or not spec 0007 has run first.

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
- Given the initial configuration, when indexing runs, then it produces at least these six
  variants: question text alone; topic + text + the image description when the question
  has one; `vector_search_queries`; topic + text + `vector_search_queries`; topic + text +
  the image description when present + `vector_search_queries`; and the image description
  alone, for questions that have an image.
- Given the two combined variants, when they are reported, then they differ on exactly one
  axis — the presence of the image description — so the contribution of that description
  is readable directly from the delta between them.
- Given a question with no image, when the topic + text variant is built, then it is topic
  + text alone — the absence of a description changes the text, never the presence of the
  variant, which is produced for every question either way.
- Given the `search_queries` variant, when indexing runs, then it is computed from
  `vector_search_queries` exactly as every other variant is computed from its own source
  text, with no special-casing anywhere in the write path.
- Given an item lacking the input a representation needs, when indexing runs, then no row
  is written for that variant and the omission is counted, never stored as a null vector.
- Given a completed indexing run, when its run artifacts are inspected, then the per-variant
  omission counts appear in the run manifest and the run log, so a representation that
  silently produced nothing for the whole bank is visible without querying the database.
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
- Given several questions sharing one image, when their image-description variants are
  computed, then that description is embedded once and the resulting vector is written to
  each of those questions' variant rows — the number of embedding calls for this arm
  matches the number of distinct images, not the number of image questions.

### FR-6: The quiz flow writes through a domain store step, and the generic sink is removed

The quiz indexing flow gains a terminal step that owns the whole quiz write — questions,
variant rows and images — and the truncate-based generic sink it replaces is deleted.

*Moved here from spec 0010's FR-4 on 2026-08-06: the step cannot be replaced without
dropping `QuizQuestionEntity.embedding`, which is this spec's data model (AD-2).*

**Acceptance criteria:**
- Given an enriched quiz item, when the flow's terminal step runs, then it upserts the
  question on `number`, obtains the row's `id`, and writes that question's variant rows
  and image row against it, in one step rather than three separately wired ones.
- Given a question already present from a previous run, when indexing re-runs, then its
  `id` is unchanged and its existing variant rows are updated rather than duplicated —
  the upsert contract spec 0010 defines, applied to the quiz tables.
- Given a question whose `number` is absent from the run's input, when the run completes,
  then it is gone from `quiz_questions`, and its variant rows follow through
  `ON DELETE CASCADE`.
- Given the codebase after this change, when `DbStoreStep` and the `StoreRepository`
  protocol are searched for, then neither is defined nor imported anywhere in `src/`
  or `tests/`.
- Given any `ingest prepare` or `ingest index` run, when it executes, then it issues no
  `TRUNCATE` against any table — completing across both domains what spec 0010 achieved
  for knowledge alone.
- Given the two quiz integration tests that fail against the target schema before this
  spec, when the suite runs after it, then both pass, because the write path no longer
  names the dropped `embedding` column.

## Non-Goals

- **Changing the corpus-side representation** — `article_commas` continues to embed
  article title + comma text. This spec varies the query side only; varying both at once
  would make the results uninterpretable. The variant-table pattern in AD-2 applies
  equally to the corpus side and makes that experiment cheap to run later, once the query
  side has a winner to hold fixed.
- **Implementing hybrid search** — the fusion arm in FR-3 fuses several **dense** rankings
  as a measurement. Fusing dense with full-text search remains a separate, still-unfunded
  decision that spec 0007's measurements inform. Spec 0007's Non-Goal is scoped to that
  dense+FTS combination precisely so it does not forbid the dense-only fusion required here.
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
- **The premise of this decision expired on 2026-08-06.** The development volume was
  recreated, `db/init.sql` ran with the spec 0008 schema, and every row was lost: the 7098
  quiz vectors, the 3650 corpus vectors, everything. There is nothing left to preserve and
  nothing left to migrate — the script's data-moving step is a no-op against a database
  that already has the target schema and no `quiz_questions.embedding` column. The script
  is **kept**, because it remains the correct and only path for any database still on the
  old schema, and because ADR 0010 requires every schema change to ship one; but the
  argument that chose a migration over a reset no longer describes this repository's
  situation. Every vector this spec touches must now be computed from scratch, which is
  what FR-4 already guarantees is cheap: the enriched layer on disk is intact, so the cost
  is embeddings only, with no LLM enrichment re-run.
- **The migration alone does not deliver the preservation it promises.** Moving the vectors
  into the variant table only keeps them until the next quiz indexing run, which under the
  write path in place when this spec was drafted truncates `quiz_questions` and reinserts
  it — cascading the migrated rows away, and in fact failing outright, since Postgres
  refuses to truncate a table a live foreign key references. The baseline therefore
  survives only if the write path upserts on the natural key and keeps `quiz_questions.id`
  stable across runs, which is spec 0010's subject. **Spec 0010 is a prerequisite of this
  spec**, not an optional companion: implementing FR-2 against a truncate-based write path
  silently destroys the very baseline FR-2 exists to protect.

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

### AD-7: The variant set is a registry in code, with the enabled names in configuration
- **Rationale:** A representation is a name *and* a rule for building the text it embeds —
  "topic + question text" is a function, not a value, so it cannot live in YAML. But the
  choice of which representations a run computes is exactly the kind of thing that must
  change without touching code, since FR-2's whole premise is that the arm set is still
  under investigation. Splitting the two puts the text-builders in a code registry keyed by
  variant name and the enabled names in `IngestorConfig`, so adding an idea is one builder
  plus one config line, and disabling one is a config line alone. It also keeps a single
  spelling of each variant name shared between the write path and the harness, which
  otherwise would have to agree by convention across three places.
- **Rejected alternatives:** The full definition in YAML — would require expressing text
  composition as data, i.e. inventing a small template language for no benefit. The full
  definition in code with no config — makes disabling an arm a code edit, which is the cost
  AD-2 set out to remove. A name-only config with builders resolved by naming convention —
  a typo becomes a silently missing arm instead of a startup error.

### AD-8: The image-description arm embeds each distinct description once and fans out
- **Rationale:** 4147 questions reference 427 distinct images, so computing this arm per
  question would issue roughly ten embedding calls for every text that has exactly one
  value. The vectors would be identical, so the stored result is the same either way; only
  the cost and the runtime differ. Deduplicating on the description before embedding and
  then writing the resulting vector to each referencing question's variant row is the same
  shape ADR 0003 already established for the vision call that produced the description in
  the first place — group by image, call once, broadcast.
- **Rejected alternatives:** Embedding per question — pays ten times over for identical
  vectors, and inflates this spec's stated re-embedding budget without changing a single
  stored value. Storing the image variant on `quiz_images` instead of per question — would
  make the arm unqueryable alongside the others, since every other variant is keyed by
  question and the harness compares arms question by question.

### AD-10: `DbStoreStep` and the `StoreRepository` protocol are deleted, not rewritten
*Moved here from spec 0010's AD-4 on 2026-08-06, with FR-6; the reasoning is unchanged.*
- **Rationale:** The generic sink has exactly one consumer, the quiz indexing flow, and
  that flow needs to resolve parent ids in order to write child rows — a domain concern,
  the same one that already justified a bespoke step on the knowledge side. Rewriting the
  generic step with upsert semantics would leave an abstraction with no caller; keeping it
  as-is would preserve a truncate-based contract that nothing satisfies and that the
  schema now rejects.
- **Rejected alternatives:** Adapting `DbStoreStep` to upsert — an abstraction kept alive
  for a consumer that no longer exists. Leaving it in place as deprecated — dead code,
  which the project's conventions require removing rather than annotating.

### AD-9: The embedding service takes texts; the `Embeddable` protocol is removed
- **Rationale:** `Embeddable` exposes one read-only `embedded_text` property, so an object
  has exactly one text to embed. That is precisely the assumption multi-variant embedding
  breaks: one question must yield five different texts. The protocol cannot express that
  without making `embedded_text` depend on state outside the object — either the object is
  mutated between passes, or the property reads a configuration saying which fields count
  right now. Both turn a pure rendering into a function of hidden state, so two callers
  embedding the same question can legitimately disagree about what its text is. Passing the
  texts directly reduces the service to what it actually does — strings in, vectors out,
  aligned 1:1 — and leaves the variant registry of AD-7 as the single place that decides
  what any variant embeds. The knowledge side loses nothing: `EmbeddableArticleComma`
  keeps its rendering, the call site just reads it before calling instead of the service
  reaching in.
- **Rejected alternatives:** Keeping `Embeddable` and running one embedding pass per
  variant with a parameterized field set — the property stops being a pure function of the
  object, which is the defect above, and it serializes five passes over the bank for no
  gain. A throwaway per-variant wrapper class implementing `Embeddable` — allocates five
  wrapper objects per question purely to carry a string the caller already holds, and adds
  one class per variant to a registry that already names them.

## Data Model

**`quiz_questions`** — gains `vector_search_queries TEXT[]` (nullable, alongside
`core_concepts` and `exact_keywords`); loses `embedding VECTOR(1536)`, which moves to the
variant table below.

**`quiz_question_embeddings`** (new) — one row per question per representation:

| Column | Notes |
|---|---|
| `quiz_question_id BIGINT` | FK to `quiz_questions(id)`, `ON DELETE CASCADE` |
| `variant TEXT` | names the text embedded: `text`, `topic_text`, `search_queries`, `combined`, `combined_description`, `image_description` (final spellings are the AD-7 registry's, and must satisfy FR-2's naming criterion) |
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

`IngestorConfig` already names `quiz_questions_table` and
`quiz_question_embeddings_table` but has no `quiz_images_table`; FR-5 needs it, in both
the settings class and the base yaml. The test-data profile inherits table names, so it
needs no corresponding entry.

Writing a variant row requires its question's `quiz_questions.id`, which is
DB-generated. The mechanism already exists on the knowledge side — a write that returns
the generated ids in input order, zipped back against the items by natural key — and the
quiz store step follows it rather than inventing a second approach. Under AD-2 those ids
must also be *stable* across runs, which is spec 0010's contribution.

`article_commas` and `articles` are untouched *by this spec* — nothing here reads,
rewrites, or re-embeds them. (Spec 0010 changes how those two tables are written, but not
what they hold. Both are currently empty and need an `ingest index knowledge` run of their
own, which is a consequence of the volume being recreated, not of this spec.)

Migration: against the current development database there is nothing to apply — it was
created from `db/init.sql` and already carries the target schema, so
`db/migrations/0008_quiz_query_representations.sql` is a no-op there. The script remains
the required path for any database still on the previous schema, and `db/init.sql` remains
the definition of the target state for freshly created volumes. What the database actually
needs is a full re-index: `ingest index quiz` to populate `quiz_questions`,
`vector_search_queries`, `quiz_images` and every variant including `search_queries`, and
`ingest index knowledge` per source to repopulate the corpus.

## Constraints

- **The repository is half-migrated, and the risk this constraint warned about has now
  materialised.** `db/init.sql` carries the target schema (committed in `764440b`), while
  `QuizQuestionStoreRepository` and `QuizQuestionEntity` still write and declare
  `quiz_questions.embedding`. The warned-of consequence — that creating a fresh Postgres
  volume runs `db/init.sql` automatically and yields a database on which `ingest index
  quiz` fails — is what actually happened on 2026-08-06. **The development database is now
  on the target schema and empty, and `ingest index quiz` fails against it**, as two
  integration tests already demonstrate. There is no longer a "before this spec lands"
  path to protect: the write path must be implemented for the database to be usable at
  all.
- **The two quiz integration tests that fail against the target schema are this spec's to
  fix.** They fail because `QuizQuestionStoreRepository` still names the dropped
  `embedding` column; FR-6 removes it. Spec 0010 deliberately leaves them red.
- **Spec 0010 must land first**, for two reasons that survive the loss of the baseline:
  the current write path truncates `quiz_questions`, which Postgres refuses outright while
  `quiz_question_embeddings` references it; and variant rows accumulate across runs, which
  requires `quiz_questions.id` to be stable rather than reissued on every reload.
- The migration script must still preserve `quiz_questions.embedding` as the
  `search_queries` variant **before** dropping the column, for any database still holding
  that column. Against the current development database the step is a no-op, since the
  column and the data are both already gone.
- The image-description arm's embedding calls must be counted per distinct image (427),
  not per image question (4147). Both produce identical stored vectors, so a per-question
  implementation is pure waste and breaks the cost budget below.
- `IngestorConfig` must gain a `quiz_images_table` entry alongside the existing
  `quiz_questions_table` and `quiz_question_embeddings_table`; FR-5 has no configured
  destination without it.
- `article_commas` and `articles` must come through the migration untouched; a run that
  re-embeds the corpus has done something wrong.
- The migration must be idempotent and transactional: re-running it is a no-op, and a
  failure leaves the schema unchanged rather than half-applied.
- `db/init.sql` and the migration must produce identical schemas, verified by the
  equivalence check rather than assumed.
- Vector parameters use the explicit `%s::vector` cast, per
  `.claude/rules/code-conventions.md`.
- Entities model the insertable projection of the row: under AD-2 the quiz entity carries
  no vector field at all, and a separate entity models a `quiz_question_embeddings` row,
  with DB-generated columns absent, per the same rules file.
- Re-embedding cost must stay within a few cents. With nothing left to migrate and six
  variants, the quiz side is roughly 36 000 items — `text`, `topic_text`,
  `search_queries`, `combined` and `combined_description` at ~7100 each, plus ~427
  distinct image descriptions under AD-8 — at `text-embedding-3-small` rates. The 3650
  corpus commas must also be re-embedded, but by `ingest index knowledge`, which is
  outside this spec.
- No new runtime dependency.

## Feasibility Evidence

- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py:54` — the mapper docstring states it drops `vector_search_queries` as "embedder input only, not persisted", the exact behaviour FR-1 reverses (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `docs/adr/0002-flatten-quiz-metadata-columns.md:11` — lists `vector_search_queries` among the metadata fields, establishing the flattening precedent this extends (verified 2026-08-05 @ 6d96b7d)
- **AD-1** — supported by: `db/init.sql:41` — `core_concepts TEXT[]` shows the column shape and nullability the new column follows (verified 2026-08-05 @ 46fad9a)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/repositories/db/quiz_question_store_repository.py:17` — the write path still lists a single `"embedding"` column, the shape this decision replaces (verified 2026-08-05 @ 46fad9a)
- **AD-2** — supported by: `src/domain/entities/quiz/quiz_question.py:22` — the entity's single `embedding: list[float] | None` field, which this decision removes in favour of variant rows (verified 2026-08-05 @ 46fad9a)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/embedded_quiz.py:21` — the intermediate model's single `embedding` field, the second place the variant split lands (verified 2026-08-05 @ 46fad9a)
- **AD-3** — supported by (historical, `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py` was line-24-and-up at the time, since deleted by `75826e3` per AD-9): `embedded_text` joined `vector_search_queries`, the single representation all four arms were measured against; deletion confirmed at `specs/0008-quiz-query-representations.md:647` (verified 2026-08-05 @ 6d96b7d)
- **AD-3** — supported by (historical, `src/guidami_ai_patente_ingestor/services/quiz/embed_quiz_metadata.py` was line-11-and-up at the time, since deleted by `75826e3`): `EmbedQuizMetadata` computed exactly one vector per item, the step FR-2 generalises; deletion confirmed at `specs/0008-quiz-query-representations.md:650` (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `src/commons/ai/embedding/configs/embedding_config.py:17` — the comment states `dimensions` "must match `vector_dim` and the `VECTOR(N)` column size", confirming dimension is fixed per column and cannot vary per row (verified 2026-08-05 @ 6d96b7d)
- **AD-6** — supported by: `src/commons/ai/embedding/clients/sentence_transformer_embedding_client.py:27` — a second, alternative embedding client already exists whose dimension differs from the production one, so more than one vector width is a real case and not hypothetical (verified 2026-08-05 @ 46fad9a)
- **AD-4** — supported by: `docker/docker-compose.yml:13` — `init.sql` is mounted read-only into `/docker-entrypoint-initdb.d/`, so it executes only on volume creation and can never alter an existing database; a migration path is therefore required, not optional (verified 2026-08-05 @ 46fad9a)
- **AD-4** — supported by: `db/init.sql:26` — `article_commas.embedding VECTOR(1536)`, the 3650 corpus vectors a reset would discard although this spec does not touch them (verified 2026-08-05 @ 46fad9a)
- **AD-5** — supported by: `docs/adr/0003-group-road-sign-description-by-image.md:24` — "Group by the image filename only", establishing that a description belongs to an image rather than to a question (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/mappers/quiz_mapper.py:52` — the mapper discards `image_description` as not persisted, the behaviour FR-5 reverses (verified 2026-08-05 @ 6d96b7d)
- **AD-5** — supported by: `src/guidami_ai_patente_ingestor/models/quiz/embedded_quiz.py:20` — `image_description: str | None` exists on the intermediate model, so the text is already carried to the storage boundary and only needs a destination (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:75` — documents that the embedding comes from `vector_search_queries` rather than the quiz text, confirming the indexing flow is the single place to extend (verified 2026-08-05 @ 6d96b7d)
- **AD-4** — supported by (historical, `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/db_store_step.py` was line-23-and-up at the time, since deleted by `608a546` per AD-10): the quiz store step called `truncate()` then `bulk_insert()`, so the run that populates the new variants would have cascaded the migrated baseline away; this is what made spec 0010 a prerequisite rather than a companion; deletion confirmed at `specs/0008-quiz-query-representations.md:631` (verified 2026-08-06 @ 2d741ac)
- **AD-7** — supported by (historical, `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py` was line-24-and-up at the time, since deleted by `75826e3` per AD-9): `embedded_text` built the embedded string in Python (`"\n".join(...)`), showing text composition is code and cannot be expressed as a YAML value; deletion confirmed at `specs/0008-quiz-query-representations.md:647` (verified 2026-08-06 @ 2d741ac)
- **AD-7** — supported by: `configs/ingestor_config.yaml:62` — `quiz_embedding_variant: search_queries` already carries a variant *name* through configuration, so splitting name-in-config from builder-in-code extends an arrangement that exists rather than introducing one (verified 2026-08-06 @ 2d741ac)
- **AD-8** — supported by: `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py:66` — `_group_by_image` collapses the questions sharing a filename into one group so a single call serves them all, the group-and-broadcast shape this decision reuses for embedding (verified 2026-08-06 @ 2d741ac)
- **AD-8** — supported by: `src/commons/ai/embedding/services/embedding_service.py:41` — `execute` returns vectors aligned 1:1 with its input and in the same order, which is what makes embedding a deduplicated list and mapping the results back to every referencing question safe (verified 2026-08-06 @ 2d741ac)
- **AD-9** — supported by (historical, `src/commons/ai/embedding/services/protocols/embeddable.py` was line-8-and-up at the time, since deleted by `d09ca49`): `Embeddable` declared a single read-only `embedded_text` property, so one object carried exactly one text to embed, which is the assumption five variants per question break; deletion confirmed at `specs/0008-quiz-query-representations.md:647` (verified 2026-08-06 @ 2d741ac)
- **AD-9** — supported by: `src/commons/ai/embedding/services/embedding_service.py:60` — the protocol is consumed in exactly one expression, `[item.embedded_text for item in batch]`, so the service needs only the strings and nothing else about the objects (verified 2026-08-06 @ 2d741ac)
- **AD-9** — supported by (historical, `src/guidami_ai_patente_ingestor/models/quiz/quiz_metadata.py` was line-24-and-up at the time, since deleted by `75826e3`): `embedded_text` rendered one fixed string (`"\n".join(self.vector_search_queries)`), showing the per-object rendering was hardcoded and could not vary per variant without external state; deletion confirmed at `specs/0008-quiz-query-representations.md:647` (verified 2026-08-06 @ 2d741ac)
- **AD-10** — supported by (historical, `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:134` was the sole `DbStoreStep` construction site at the time, since replaced by `StoreQuizStep`): the quiz indexing flow was the only place constructing a `DbStoreStep`, so replacing that step left the generic sink with no consumer at all; replacement confirmed at `specs/0008-quiz-query-representations.md:631` (verified 2026-08-06 @ 91c4fe7)
- **AD-10** — supported by (historical, `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/protocols/store_repository.py` was line-5-and-up at the time, since deleted by `608a546`): the protocol's docstring defined it as the "contract for a full-reload store (truncate + bulk insert)", a contract the current schema rejects outright; deletion confirmed at `specs/0008-quiz-query-representations.md:631` (verified 2026-08-06 @ 91c4fe7)
- **AD-10** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/store_articles_and_commas_step.py:20` — a domain-specific store step resolving parent ids already exists, and is the shape FR-6's quiz step follows (verified 2026-08-06 @ 91c4fe7)

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
- [ ] **non-blocking** — After the winning arm is chosen, do the losing variants stay in
  the table as permanent experiment scaffolding, or are they deleted? Under AD-2 this is a
  `DELETE`, not a schema change. — owner: user

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-06
- **Feasibility asserted:** by write-spec on 2026-08-05, based on Feasibility Evidence above

## Changelog

- **2026-08-06** — **Received FR-6 and AD-10 from spec 0010** (its FR-4 and AD-4), a
  material scope addition the user approved in conversation the same day. Found during
  0010's plan extraction: removing `DbStoreStep` requires re-pointing the quiz flow at a
  new terminal step, which is impossible without dropping `QuizQuestionEntity.embedding`
  and its repository column — data-model shape this spec's AD-2 already owns. Since this
  spec already owned every other part of the quiz write path (entity, repository, variant
  rows, images), the boundary now follows the code rather than cutting across it. FR-6
  also absorbs the Constraint that the two failing quiz integration tests must pass, which
  0010 could not satisfy.
- **2026-08-06** — Second amendment of the day, after three developments. **(1) The
  baseline is gone.** The development volume was recreated, `db/init.sql` ran with the
  spec 0008 schema, and every row was lost — the 7098 quiz vectors, the 3650 corpus
  vectors, all of it. AD-4 chose a migration over a reset specifically to preserve those
  vectors, so its premise no longer describes this repository; the decision now records
  that, the two FR-2 acceptance criteria asserting the baseline is moved and survives are
  replaced by one requiring `search_queries` to be computed like every other variant, the
  half-migrated Constraint records that the risk it warned about materialised, and the
  cost constraint rises from ~25 000 to ~28 500 items now that nothing is migrated in. The
  migration script is **kept**: it is still the only correct path for a database on the
  old schema, and ADR 0010 requires one per schema change. The 0010 prerequisite survives
  on its two remaining legs — TRUNCATE fails against the foreign key, and variant rows
  accumulating across runs need stable parent ids. **(2)** On user request, the topic +
  text variant now also carries the image description when the question has one; a
  question without an image still produces the variant, just from topic + text alone.
  **(3) New AD-9**: `EmbeddingService` takes texts and the `Embeddable`/`Embedded`
  protocols are removed. Raised by the user: `embedded_text` is a single read-only
  property, so one object has exactly one text to embed, which is the assumption five
  variants per question breaks — keeping the protocol would require either mutating the
  object between passes or having the property read external configuration, both of which
  make the rendering depend on hidden state. **(4)** On user request, a sixth variant is
  added rather than folding the image description into the existing `combined`:
  `combined` keeps topic + text + `vector_search_queries`, and `combined_description` adds
  the image description on top. Keeping both means the two differ on exactly one axis, so
  the description's contribution is readable as a delta instead of being confounded with
  the search queries' — at the cost of ~7100 further embeddings, which AD-2's row-per-
  variant table absorbs without a schema change.
- **2026-08-06** — Amended after verifying the spec against the working tree. The
  correction that matters: **AD-4's preservation guarantee was unreachable.** The
  migration moves the 7098 existing vectors into the variant table, but the run the spec
  then prescribes — re-run quiz indexing — goes through a store step that truncates
  `quiz_questions` and reinserts it, which cascades the migrated rows away, and in fact
  fails outright because Postgres refuses to truncate a table a live foreign key
  references (two integration tests already fail for this reason). AD-4 gained a bullet
  saying so, and **spec 0010 (upsert write path) is now recorded as a prerequisite**, with
  a matching Constraint and a new FR-2 acceptance criterion requiring the baseline to
  survive the run that fills the rest of the table. Also added: **AD-7**, putting the
  variant registry in code with the enabled names in configuration (a representation is a
  name *and* a text-building rule, and a rule cannot be a YAML value) — FR-2 required
  "each configured representation" without saying where that configuration lives;
  **AD-8**, embedding each distinct image description once and fanning the vector out to
  every question referencing it (427 distinct descriptions serve 4147 questions, so a
  per-question implementation pays ten times over for identical vectors and breaks the
  stated cost budget); an FR-2 acceptance criterion putting the per-variant omission
  counts in the run manifest and log, since the existing criterion said the omission is
  "counted" without saying where; and Data Model notes for the missing
  `IngestorConfig.quiz_images_table` and for the DB-generated-id acquisition the variant
  rows need, whose mechanism already exists on the knowledge side.
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

- **2026-08-05** — Amended after an independent adversarial review of spec 0007 that also
  covered this spec. Corrections: three Feasibility Evidence entries cited **this spec's own
  deliverables** (`db/init.sql` lines added by `764440b`, and the migration script itself) —
  a deliverable cannot establish its own feasibility, so they are replaced by the
  pre-existing facts that motivate the decisions (the read-only `init.sql` mount, the 3650
  corpus vectors a reset would discard, the second embedding client whose dimension
  differs). A fourth entry pointed at a line the same commit had shifted. Residual
  "three vector columns" wording surviving the AD-2 reversal to variant rows was corrected in
  Constraints and Open Questions, as was a Data Model sentence claiming `articles` and
  `article_commas` are "re-populated by the reset" — there is no reset, and the neighbouring
  constraint already said a run that re-embeds the corpus is a defect. FR-2's
  "reproduces the 0007 baseline exactly" is restated as what the migration actually does:
  it *moves* the existing vectors. The hybrid-search Non-Goal now states explicitly that
  spec 0007's matching Non-Goal is scoped to dense+FTS, so it does not forbid the dense-only
  RRF arm this spec requires — the two specs previously contradicted each other outright.

### 2026-08-07 — plan executed: plans/0008-quiz-query-representations-phase1-plan.md

- **DoD result:** all items verified mechanically — full non-integration suite (620 passed),
  integration suite (39 passed, 1 skipped) against the ephemeral `docker-compose.test.yml`
  Postgres, `ruff check`/`ruff format --check`/`pyright` all clean. All 8 tasks confirmed
  against current repo state: `quiz_images_table` config, `QuizImageEntity`,
  `QuizImageStoreRepository`, `QuizQuestionEntity`/`QuizQuestionStoreRepository` dropping
  `embedding` and adding `vector_search_queries` + `delete_missing`, `QuizMapper.
  from_embedded_to_quiz_images`, `StoreQuizStep`, `quiz_flows.py` rewired with `DbStoreStep`/
  `StoreRepository` fully deleted (zero remaining callers, AD-10), `quiz_images` registered
  in CLI wiring health checks.
- **Deviations from plan:** none.
- **Learnings:** none beyond what's already recorded in this spec's own changelog above.
- **Status change:** ready → implemented — confirmed by Alessio Gilardi, 2026-08-07 (the
  intermediate `in-progress` flip was skipped at extraction time for both this plan and
  Phase 2; the user chose to close directly from `ready` rather than retroactively inserting
  the missing transition).

### 2026-08-07 — plan executed: plans/0008-quiz-query-representations-phase2-plan.md

- **DoD result:** all items verified mechanically — full non-integration suite (620 passed),
  integration suite (39 passed, 1 skipped) against the ephemeral `docker-compose.test.yml`
  Postgres (including FR-6's two previously-failing quiz integration tests and the new
  `test_quiz_flows_integration.py`, all now green), `ruff check`/`ruff format --check`/
  `pyright` all clean. All 17 tasks confirmed against current repo state: `EmbeddingService.
  execute(Sequence[str])` with `Embeddable`/`Embedded` and the dead generic `EmbedStep`
  deleted; `EmbeddableQuizVariant`/`EmbedQuizVariantsResult`; `quiz_variant_registry.py` +
  `IngestorConfig.quiz_embedding_variants` (all six variants configured); `EmbedQuizVariants`
  replacing `EmbedQuizMetadata`; `QuizQuestionEmbeddingEntity`/
  `QuizQuestionEmbeddingStoreRepository` (upsert on `(quiz_question_id, variant)`,
  deliberately no `delete_missing`, PD-6); `StoreQuizStep` extended to all three quiz tables,
  resolving `quiz_question_id` via `upsert_returning_ids` before writing variant rows;
  `quiz_flows.py` rewired onto `EmbedQuizVariants`; `IndexManifest.
  quiz_variant_omissions`; `QuizReadRepository.populated_model_columns()`/generalized
  `fetch_with_vectors`; `RankingDelta`/`ArmResult`/`MultiArmEvaluationSummary`; decoupled
  `RetrievalEvaluator`; `reciprocal_rank_fusion` (`commons/ai/utils/`, relocated from an
  initial `commons/retrieval/` placement on user request after this plan's own T-15 landed);
  `MultiArmRetrievalEvaluator` + `EvaluationConfig.rrf_k=60`; `evaluate.py` wired onto
  `MultiArmRetrievalEvaluator`. File discipline: every touched file landed across 5
  dependency-ordered commits (`d09ca49`, `75826e3`, `f8095c6`, `69fa15b`, plus the unrelated
  standalone `d575fdb`), each verified scoped via `git diff --cached` before committing.
- **Deviations from plan:** (1) Task T-11's own plan text already self-records that the
  assumed committed `data/test-data/enriched/quiz-patente-ab/` fixture didn't exist, so a
  `tmp_path`-based fixture was used for the FR-4 integration test instead — consistent with
  FR-4's own non-goal of not re-running LLM enrichment. (2) `data/test-data/enriched/` was
  subsequently generated for real and committed (`69fa15b`) via a new `test_data_sampler`
  capability (`sample_quiz_enriched`) that copies the sampled quiz subset's already-enriched
  files rather than re-running enrichment — ahead of when the plan anticipated this fixture
  would exist. (3) `reciprocal_rank_fusion` was committed under `commons/retrieval/` by this
  plan's T-15, then relocated to `commons/ai/utils/` in a same-session follow-up at the
  user's explicit request (a generic, domain-agnostic utility per the `utils/` convention in
  `rules/python/architecture.md`), before any of Phase 2's commits landed — so the final
  committed location differs from what T-15 specified, but the function and its public API
  are unchanged.
- **Learnings:** the write-plan → implementation handoff has no mechanical enforcement of the
  `ready → in-progress` flip at extraction time — both this plan and Phase 1's were extracted
  while the spec sat at `ready`, and nothing caught the missing transition until this
  close-plan run. Worth considering for a future process amendment, not addressed here since
  the user chose to close directly rather than retroactively backfill the transition.
- **Status change:** ready → implemented — confirmed by Alessio Gilardi, 2026-08-07 (see
  Phase 1's entry above for the shared rationale).
