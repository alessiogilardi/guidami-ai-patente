# Spec 0010: Upsert Write Path

| | |
|---|---|
| **Id** | 0010 |
| **Status** | implemented |
| **Date** | 2026-08-06 |
| **Discussion log** | none — compiled directly from conversation |
| **Supersedes / superseded by** | — |

## Problem & Motivation

Every ingest run empties the table it is about to write and reinserts it wholesale.
That was sound while each table stood alone, and it is the invariant the project
documented: `DbStoreStep` calls `truncate()` then `bulk_insert()`, and
`StoreArticlesAndCommasStep` deletes a source's articles before reinserting them.

It stops being sound the moment a second table references the first by its
DB-generated `id`. A full reload discards every `id` on every run, so any child row
pointing at those ids is destroyed along with them — and `BIGSERIAL` hands out new
ones, so nothing can be stitched back. `article_commas` already lives with this by
being rebuilt from scratch on every knowledge run. `quiz_question_embeddings` cannot:
its whole purpose is to accumulate query representations across runs, including
vectors that were migrated in rather than computed, and that no run recomputes.

Postgres makes the collision explicit rather than silent. It refuses to `TRUNCATE`
a table referenced by a live foreign key unless the referencing table is named in
the same statement — a fact this codebase already discovered once, on the knowledge
side, and documented. So the current quiz write path does not merely lose data
against the new schema; it fails outright. Two integration tests already fail for
exactly this reason.

The narrow fix — truncate both tables together — trades a crash for silent
destruction: it would wipe the very rows a data-preserving migration was written to
save. The write path itself is what needs to change.

## Functional Requirements

### FR-1: Ingest runs write through upsert, preserving row identity

An ingest run updates the rows it already wrote in a previous run instead of
replacing them, so every row keeps its `id` across runs.

**Acceptance criteria:**
- Given a table holding a row written by a previous run, when a run writes an item
  carrying the same natural key, then the existing row's non-key columns take the new
  values and its `id` is unchanged.
- Given a table holding a row written by a previous run, when a run writes an item
  carrying a natural key not yet present, then a new row is inserted.
- Given a parent row whose `id` is referenced by child rows, when a run re-writes
  that parent, then the child rows still exist and still reference it.
- Given an `ingest index knowledge` run, when it executes, then it issues no `TRUNCATE`
  against any table. The quiz indexing flow still truncates until spec 0008 replaces its
  store step; extending this criterion to every command is that spec's FR-6.

### FR-2: A run deletes what disappeared from its source layer, within its own scope

Removal survives the loss of truncate: a run reconciles its target away from rows
whose natural key is no longer present in its input.

**Acceptance criteria:**
- Given a row inside the run's scope whose natural key is absent from the run's
  input, when the run completes, then that row is no longer in the table.
- Given a row outside the run's scope, when the run completes, then that row is
  unchanged — a run over one knowledge source never deletes another source's rows.
- Given a parent row removed by reconciliation, when it is deleted, then its child
  rows are removed by the existing `ON DELETE CASCADE`, with no second statement
  targeting the child table.
- Given a run whose input is identical to what the table already holds, when it
  completes, then no row was deleted and every `id` is unchanged.

### FR-3: `reset` remains the only destructive command, and works against the current schema

Destruction is concentrated in one explicitly gated command, which succeeds on a
schema where `quiz_questions` is referenced by a foreign key.

**Acceptance criteria:**
- Given `ingest reset quiz --apply` and a schema where `quiz_question_embeddings`
  references `quiz_questions`, when it runs, then the command succeeds and both
  tables are left empty.
- Given `ingest reset` without `--apply`, when it runs, then it prints the preview
  and opens no database connection, exactly as before this change.
- Given the knowledge indexing path after this change, when destructive statements are
  searched for, then no `TRUNCATE` reaches it — the only remaining one outside `reset`
  is `DbStoreStep`, still wired to the quiz flow until spec 0008's FR-6 removes it.

### ~~FR-4: The generic full-reload step is removed~~

**Moved to spec 0008 as FR-6** on 2026-08-06. Removing `DbStoreStep` requires replacing
the quiz flow's terminal step, which cannot be done without dropping the `embedding`
field from `QuizQuestionEntity` and its repository's column list — data-model shape that
spec 0008's AD-2 already owns. Keeping the requirement here would have made this spec
unimplementable without reaching into another spec's data model.

## Non-Goals

- **Introducing a migration tool** — this spec changes how rows are written, not how
  schemas evolve. `db/init.sql` plus `db/migrations/` remains the arrangement
  ADR 0010 accepted.
- **Making a run atomic** — `PostgresClient` connects with `autocommit=True`, so
  upsert and reconciliation are separate statements. This spec does not add
  transaction management; it deliberately leaves the failure exposure no worse than
  the current truncate-then-insert sequence, which is equally non-atomic. See Open
  Questions.
- **The quiz write path, in its entirety** — `QuizQuestionStoreRepository`, the quiz
  store step, the repositories for `quiz_question_embeddings` and `quiz_images`, and the
  removal of `DbStoreStep` are all spec 0008's deliverables (its FR-6 and AD-10). This
  spec defines the upsert contract they must follow and provides the shared base they
  build on; it does not touch the quiz side itself. The one exception is `ingest reset
  quiz`, which FR-3 fixes here because it needs no entity change.
- **Removing the `embedding` field from `QuizQuestionEntity`** — data-model shape owned
  by spec 0008's AD-2. It is why FR-4 moved there: without it the quiz flow cannot be
  re-pointed at a new store step.
- **Changing what gets embedded or ingested** — no model, mapper, enricher, or
  embedding call is touched. The set of rows a run produces is identical before and
  after; only how they reach the table changes.
- **Adding a vector index** — unchanged, still an exact scan.

## Architectural Decisions

### AD-1: Rows are written with `INSERT ... ON CONFLICT` on the table's natural key
- **Rationale:** Every table this spec touches already declares the unique constraint
  an upsert needs, so the conflict target is a fact of the existing schema rather than
  something to invent. Upserting keeps `id` stable, which is the property child tables
  depend on and which a full reload structurally cannot offer. It also sidesteps the
  `TRUNCATE`-under-foreign-key refusal entirely, instead of working around it.
- **Rejected alternatives:** Naming both tables in one combined `TRUNCATE` — turns a
  loud crash into silent destruction of vectors that no run recomputes, and leaves ids
  churning for every future child table. Upserting on the quiz side only and leaving
  knowledge on truncate — two write-path idioms in one codebase for no reason, and
  `article_commas` has the same parent-id fragility, merely unexercised so far.

### AD-2: Upsert is paired with a reconciling delete scoped to what the run owns
- **Rationale:** Upsert never removes, so on its own it silently converts the store
  from "the database mirrors the layer on disk" into "the database accumulates
  everything ever ingested" — a repealed article or a deduplicated question would
  linger and keep being retrieved. Scoping the delete to the run's own territory
  (a knowledge run's `source`; the whole bank for quiz, which has a single source)
  preserves today's mirror semantics exactly while leaving every other source
  untouched. The reconciling delete is what makes the change behaviour-preserving
  rather than behaviour-altering.
- **Rejected alternatives:** Pure upsert with unbounded accumulation — discards a
  documented guarantee, and the test-data profile makes the loss immediate rather than
  theoretical, since it targets the same tables as the full corpus. Giving the
  test-data profile its own tables — hides that one symptom behind duplicated schema
  while leaving stale rows within a single corpus unaddressed.

### AD-3: `reset` survives as the sole destructive path and moves to a combined `TRUNCATE`
- **Rationale:** Removing every destructive path would leave no supported way to empty
  the database, pushing operators to raw `psql` or to deleting the bind mount. Keeping
  one command, gated behind `--apply` and preview-by-default, concentrates destruction
  where it is visible. Its quiz branch must name the referencing table in the same
  statement for precisely the reason the knowledge branch already does.
- **Rejected alternatives:** Dropping `reset` altogether — trades an auditable command
  for undocumented manual surgery. Using `TRUNCATE ... CASCADE` — already considered
  and rejected for the knowledge branch because it silently empties any future table
  that gains a foreign key, not just the one known today; that reasoning applies
  unchanged here.

### AD-4: `DbStoreStep` and the `StoreRepository` protocol are deleted, not rewritten
> **Moved to spec 0008 as AD-10** on 2026-08-06, together with FR-4. The reasoning below
> is unchanged and still governs — it is simply enacted by the spec that owns the quiz
> write path. Retained here so this spec's evidence stays intact and the decision's
> origin is traceable.
- **Rationale:** The generic sink has exactly one consumer, the quiz indexing flow,
  and that flow needs to resolve parent ids in order to write child rows — which is a
  domain concern, the same one that already justified a bespoke step on the knowledge
  side. Rewriting the generic step with upsert semantics would leave an abstraction
  with no caller; keeping it as-is would preserve a truncate-based contract that
  nothing satisfies and that the schema now rejects.
- **Rejected alternatives:** Adapting `DbStoreStep` to upsert — an abstraction kept
  alive for a consumer that no longer exists. Leaving it in place as deprecated — dead
  code, which the project's conventions require removing rather than annotating.

## Data Model

No schema change: this spec alters how rows are written, not what is stored. It
depends on unique constraints that already exist in `db/init.sql`.

| Table | `ON CONFLICT` target | Reconciliation scope |
|---|---|---|
| `articles` | `(source, number)` | the run's `source` |
| `article_commas` | `(article_id, comma_number)` | the article ids the run wrote |
| `quiz_questions` | `(number)` | the whole table — quiz has a single source |
| `quiz_question_embeddings` | `(quiz_question_id, variant)` | spec 0008 |
| `quiz_images` | `(filename)` | spec 0008 |

Only the first two rows are implemented here. The three quiz rows state the contract
spec 0008's repositories must follow, so that both specs agree on the conflict targets
before either is built; their implementation is entirely spec 0008's (its FR-6).

Deleting a reconciled-away parent removes its children through the `ON DELETE CASCADE`
already declared on `article_commas.article_id` and
`quiz_question_embeddings.quiz_question_id` — reconciliation therefore never needs a
statement of its own against a child table whose parent is being removed.

`created_at` on `quiz_questions` stops recording the load-batch time and starts
recording first ingestion, since a row is no longer recreated on every run. This is a
semantic change to an existing column, and `docs/database.md` states the old meaning
explicitly; it must be corrected there. The change lands with spec 0008's FR-6, which
is what stops recreating quiz rows — but the documentation sentence is wrong the moment
either spec ships, since it attributes the meaning to a reload strategy that is going
away on both sides.

## Constraints

- The mirror semantics currently guaranteed by truncate must be preserved: after a
  run, the rows in the run's scope must be exactly those its input produced. A change
  that leaves stale rows behind has not satisfied FR-2.
- A test-data run reconciles the full corpus away, because
  `configs/ingestor_config.test-data.yaml` inherits the base table names and quiz
  reconciliation spans the whole table. This is today's behaviour under truncate and
  is deliberately preserved, not fixed here.
- No new runtime dependency, and no change to `PostgresClient`'s connection semantics.
- `ingest reset` keeps its inverted gate: preview by default, no database connection
  opened without `--apply`.
- Vector parameters keep the explicit `%s::vector` cast rule from
  `.claude/rules/code-conventions.md`; a plain `INSERT` needs no cast, since the
  pgvector adapter is registered connection-wide.
- No currently passing test may regress. The two quiz integration tests that already
  fail against the target schema stay red after this spec: they fail because
  `QuizQuestionStoreRepository` still writes a dropped `embedding` column, which spec
  0008's FR-6 fixes. Turning them green is that spec's Definition of Done, not this one's.

## Feasibility Evidence

- **AD-1** — supported by: `db/init.sql:46` — `quiz_questions` declares `UNIQUE(number)`, the conflict target an upsert needs, already present without schema work (verified 2026-08-06 @ 2d741ac)
- **AD-1** — supported by: `db/init.sql:16` — `articles` declares `UNIQUE (source, number)`; `db/init.sql:27` does the same for `article_commas` with `UNIQUE (article_id, comma_number)`, so every table in scope already has a natural key (verified 2026-08-06 @ 2d741ac)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/db_store_step.py:23` — `execute` calls `self._store_repo.truncate()` then `bulk_insert(items)`, the full-reload behaviour this decision replaces (verified 2026-08-06 @ 2d741ac)
- **AD-1** — supported by: `src/commons/clients/postgres_client.py:51` — documents that Postgres refuses to `TRUNCATE` a table referenced by a live FK constraint unless both are named in the same statement, the failure the current quiz write path now hits (verified 2026-08-06 @ 2d741ac)
- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/repositories/db/article_store_repository.py:46` — `bulk_insert_returning_ids` already returns DB-generated ids in input order, so recovering ids from a write is an established capability, not a new one (verified 2026-08-06 @ 2d741ac)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/store_articles_and_commas_step.py:61` — `delete_source` before reinsert is the existing mechanism by which a knowledge run removes rows that vanished from its layer; the reconciling delete must preserve that effect (verified 2026-08-06 @ 2d741ac)
- **AD-2** — supported by: `configs/ingestor_config.test-data.yaml:4` — states that table names are inherited from the base yaml, confirming the test-data profile writes the same Postgres tables as the full corpus (verified 2026-08-06 @ 2d741ac)
- **AD-2** — supported by: `docs/database.md:158` — records that `created_at` reflects the load-batch time "under the truncate + bulk-insert reload strategy", the documented invariant this change replaces (verified 2026-08-06 @ 2d741ac)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/cli/commands/reset.py:56` — the quiz branch truncates `quiz_questions` alone through a single-table repository call, which the new foreign key makes fail (verified 2026-08-06 @ 2d741ac)
- **AD-3** — supported by: `db/init.sql:63` — `quiz_question_embeddings.quiz_question_id` references `quiz_questions (id)`, the constraint that breaks the single-table truncate (verified 2026-08-06 @ 2d741ac)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/quiz_flows.py:134` — the quiz indexing flow is the only place constructing a `DbStoreStep`, so removing it leaves no orphaned consumer (verified 2026-08-06 @ 2d741ac)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/protocols/store_repository.py:5` — the protocol's own docstring defines it as the "contract for a full-reload store (truncate + bulk insert)", the contract this spec abolishes (verified 2026-08-06 @ 2d741ac)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/steps/knowledge/store_articles_and_commas_step.py:20` — a domain-specific store step resolving parent ids already exists and is the shape the quiz side must adopt (verified 2026-08-06 @ 2d741ac)

## Open Questions

- [ ] **non-blocking** — Should upsert and its reconciling delete run in one
  transaction? `PostgresClient` is `autocommit=True`, so today a crash between them
  leaves stale rows until the next run. The current truncate-then-insert path is
  equally non-atomic, so this is not a regression — but it is a latent improvement
  that would require transaction support on the client. — owner: user
- [ ] **non-blocking** — Should reconciliation extend to `quiz_question_embeddings`
  rows whose `variant` is no longer produced by the run? Spec 0008 already asks
  whether losing variants are kept as experiment scaffolding or deleted; the answer
  determines whether variant rows are reconciled or left to accumulate
  deliberately. — owner: user
- [ ] **non-blocking** — Should `quiz_images` rows for images no longer referenced by
  any question be reconciled away? The table is small (427 rows) and the descriptions
  are expensive to regenerate, so keeping orphans may be preferable to deleting
  them. — owner: user

## Sign-off

- **Scope approved by user:** Alessio Gilardi, 2026-08-06
- **Feasibility asserted:** by write-spec on 2026-08-06, based on Feasibility Evidence above

## Changelog

- **2026-08-06** — **FR-4 and AD-4 moved to spec 0008** (as its FR-6 and AD-10), a
  material scope reduction the user approved in conversation the same day. Found during
  plan extraction: FR-4 required re-pointing the quiz flow at a new terminal step, which
  is impossible without dropping the `embedding` field from `QuizQuestionEntity` and its
  repository's column list — data-model shape that spec 0008's AD-2 already claims. This
  spec would therefore have been unimplementable without reaching into another spec's
  data model, and `/write-plan` correctly refuses to make that call. Spec 0008 already
  owned every other part of the quiz write path, so the boundary now follows the code:
  0010 is the mechanism plus the knowledge side, 0008 is the whole quiz side.
  Consequences recorded here: FR-1's no-`TRUNCATE` criterion is narrowed to
  `ingest index knowledge`; FR-3's third criterion acknowledges `DbStoreStep` survives
  until 0008; the Constraint requiring the two failing quiz integration tests to pass is
  reassigned to 0008; Non-Goals now exclude the quiz write path explicitly. FR-3 stays
  here in full — fixing `ingest reset quiz` needs no entity change.

### 2026-08-06 — plan executed: docs/superpowers/plans/2026-08-06-upsert-write-path-plan.md

- **DoD result:** all items verified mechanically — every per-task failing-test/
  characterization test passes (T-1 through T-6), full suite green (`uv run pytest`:
  578 passed; `uv run pytest -m integration`: 24 passed, 2 pre-existing expected
  failures in the quiz path reassigned to spec 0008, 1 skipped), `ruff format`/
  `pyright` clean, `ruff check` has one pre-existing unrelated failure
  (`tests/scrapers/test_rca_extract.py`, predates this plan). File discipline: three
  files outside any task's Files list, all inside T-6 — user-confirmed in-scope.
- **Deviations from plan:** T-6 touched three files beyond its stated Files list
  (`docs/database.md`, `docs/patterns.md`): `docs/architecture.md`, `docs/layout.md`,
  and `src/commons/ai/observability/repositories/llm_call_log_repository.py` each
  carried a stale `BulkInsertStoreRepository` reference that T-6's own verification
  command (a repo-wide grep over `docs/ src/ tests/`) required to be silent — simple
  renames, no rationale changes, accepted by the user 2026-08-06. One further stale
  reference was found and left as-is, outside the verification command's own scope:
  `.claude/rules/cli-structure.md:31` still names `BulkInsertStoreRepository` in an
  example; noted as optional follow-up, not fixed here.
- **Learnings:** when a task's Files list is narrower than a verification command it
  also specifies (T-6's grep spanned `docs/ src/ tests/`, its Files list named only
  two files), the verification command is the more precise, executable spec of
  "done" and should win — worth stating that precedence explicitly in future plans
  to avoid leaving it to the implementer's judgment.
- **Status change:** in-progress → implemented — confirmed by Alessio Gilardi,
  2026-08-06.
