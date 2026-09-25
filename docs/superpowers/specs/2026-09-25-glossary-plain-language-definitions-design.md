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

# Spec 0022: Plain-language glossary definitions

| | |
|---|---|
| **Id** | 0022 |
| **Status** | draft |
| **Date** | 2026-09-25 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`; no separate transcript file) |
| **Supersedes / superseded by** | — |
| **Extends** | Spec 0019 (definition glossary): adds a third, independent pipeline (`simplify-glossary-definitions`) and one nullable column (`definition_plain`) to the table spec 0019 owns and is the only writer of (besides this new column). Does not touch extraction, embedding, `translate-glossary-terms`, or ADR 0038's verbatim guarantee on `definition` — the one exception is a one-line addition to `GlossaryEntryWriteRepository`'s upsert (FR-1a), mirroring its existing `term_ru` reset. |
| **Coordinates with** | Spec 0021 (on-demand glossary enrichment, draft, pending sign-off — not yet implemented): both specs touch `GlossaryCandidate`, `CitedGlossaryTerm`/`CitedGlossaryTermResponse` and `ExplanationService._vocabulary_outcome`/`_deduplicated_hints`. Per the user's explicit direction, **this spec is implemented first**; spec 0021's implementation must build on top of this spec's changes to those classes, not the other way around. |

## Problem & Motivation

`glossary_entries.definition` (spec 0019) is extracted verbatim from the corpus under
ADR 0038's mechanical guarantee — by design, it is unedited normative legal text. That
text is exactly what makes it trustworthy as RAG grounding (it is what
`glossary_entries.embedding_3_small` embeds, and what `QuestionExplainerAgent`'s prompt
reads via `QuestionExplainerRequest.candidates_block`), but it is exactly what makes it
opaque to an end user: CdS/CAP definitions are written in dense legalese ("per
carreggiata si intende la parte della strada destinata allo scorrimento dei veicoli...").

`ExplanationService._deduplicated_hints` copies this same verbatim `definition` onto
every `CitedGlossaryTerm`/`CitedGlossaryTermResponse` the vocabulary stage cites
(`services/explanation_service.py:270-277`), and
`CitedGlossaryTermResponse`'s own docstring confirms it "is rendered by the bot as its
own glossary-block line" (`api/schemas/quiz_explanation.py:43-44`) — so the legalese
text this spec is about reaches the end user directly, in the bot's rendered glossary
block, not just as an internal grounding detail.

This spec adds a second, plain-language rendering of the same definition, generated
offline by a new agent, stored in a new nullable column, and read only at the one
point that actually surfaces text to a user — without touching the verbatim column, its
embedding, or ADR 0038's guarantee.

**Shapes considered and rejected during brainstorming, recorded so a future reader does
not re-propose them:**

- **Swap column semantics** — the requester's own first proposal: keep the name
  `definition` but change what it holds (plain text), and rename the current verbatim
  column to `definition_extracted`. Rejected once the actual consumers were traced:
  `definition` is the source of `embedding_3_small` (FR-6, spec 0019) and of ADR
  0038's verbatim `output_validator` guarantee. Renaming it would force every write-path
  class that currently reads/writes `definition` (`GlossaryExtractorAgent`'s validator,
  `GlossaryEntryWriteRepository`'s upsert, `GlossaryBuildService`'s embedding step) to
  be repointed at a differently-named column for no functional gain — the "consumers
  don't change" goal is achieved just as well (see FR-5) without ever touching the
  write path spec 0019 already validated.
- **A third column consumed everywhere, including the explainer's own grounding
  prompt** — rejected: `QuestionExplainerRequest.candidates_block` feeds
  `QuestionExplainerAgent`'s prompt, and grounding fidelity there is worth more than
  register consistency between the model's input and the user's output. The model reads
  the precise legal text; the user reads the plain one (FR-5).
- **Folding simplification into `build-glossary`'s own pipeline** — rejected, mirroring
  spec 0019's ADR 0039 reasoning for `term_ru` almost verbatim: a simplification
  failure must never fail, retry, or block an extraction that has nothing to do with
  it. A third, fully independent script keeps that isolation (FR-3).
- **Excluding a term from the API response until it has a plain rendering** —
  rejected: `term_ru` already established the precedent that a `glossary_entries` row
  is a complete, servable entry even when a derived column is still `NULL` (spec 0019,
  ADR 0039). Falling back to the verbatim text when `definition_plain IS NULL` keeps
  every row servable from the moment `build-glossary` writes it, with no dependency
  ordering between the two offline scripts (FR-5).

## Functional Requirements

### FR-1: A new nullable column holds the plain-language rendering

`glossary_entries` gains `definition_plain TEXT` (nullable, no `CHECK`, no `NOT NULL`),
written only by the new `simplify-glossary-definitions` script (FR-2). A freshly
inserted row leaves `definition_plain` at its column default, `NULL`.

### FR-1a: `build-glossary`'s upsert resets `definition_plain` on conflict, mirroring `term_ru`

(Added during grilling, 2026-09-25.) `GlossaryEntryWriteRepository._upsert`
(`src/glossary/repositories/glossary_entry_write_repository.py:53-58`) already resets
`term_ru = NULL` on every conflict, unconditionally — even when the re-extracted
`definition` is byte-identical to what was already stored — precisely so a `--force`
rebuild never leaves a translation pinned to a `definition` that may have changed. The
same staleness risk applies to `definition_plain`: without an equivalent reset, a
`--force` rebuild that changes a block's verbatim text (e.g. an upstream parser fix)
would silently leave the *old* plain-language rendering in place forever — nothing else
in the system ever invalidates it, since `simplify-glossary-definitions` only ever
selects rows where `definition_plain IS NULL`.

The `ON CONFLICT ... DO UPDATE SET` clause therefore also resets
`definition_plain = NULL`, alongside the existing `term_ru = NULL` reset — a one-line
addition to the same `SET` clause, not a new query or a new responsibility for the
class. This is the one and only touch this spec makes to `build-glossary`'s own write
path; extraction, chunking and embedding remain entirely unmodified (FR-3 is a
genuinely new, independent script — see Non-Goals).

### FR-2: `uv run simplify-glossary-definitions [--force] [--dry-run]`

A third script, `simplify-glossary-definitions = "glossary.simplify_main:main"`, in the
same `src/glossary/` package, structured as the mirror image of
`translate-glossary-terms` (spec 0019, FR-5):

- Reads every row with `definition_plain IS NULL` (`GlossaryDefinitionReadRepository`)
  — or, with `--force`, every row regardless of its current `definition_plain`.
- Simplifies them in batches of `GlossaryConfig.simplification_batch_size` through
  `GlossaryDefinitionSimplifierAgent` (FR-3).
- Writes each successful batch's `definition_plain` back by id
  (`GlossaryDefinitionUpdateRepository`, a plain `UPDATE`, no upsert, no
  reconciliation) — the only class that ever writes this column.
- `--dry-run` prints the step chain and exits: no filesystem write, no LLM call, no
  database connection — symmetric with `build-glossary`/`translate-glossary-terms`.
- Every real run logs to the console and to
  `logs/simplify_glossary_definitions_<timestamp>/run.log` (`RunArtifactWriter`, as the
  other two scripts).
- It ends with a summary (rows simplified, rows still `definition_plain = NULL`)
  printed to stdout.

It never touches extraction, embedding, `definition`, `term_ru`, or any block config —
symmetric with how `translate-glossary-terms` never touches those either.

### FR-3: A new, minimal agent — never touches the verbatim guarantee

`GlossaryDefinitionSimplifierAgent` (`agents/glossary_definition_simplifier/`, config
`configs/agents/glossary_definition_simplifier.yaml` — Italian output, unsuffixed per
`.claude/rules/agent-config-naming.md`) receives one batch's `{term, definition}` pairs
and returns, per entry, a `definition_plain`: the same legal meaning rewritten in
plain, everyday Italian a learner driver understands — no article/comma citations, no
legal jargon, 1-2 short sentences.

Unlike `GlossaryExtractorAgent`, this agent has **no verbatim constraint** — rewriting
is its entire job, the opposite invariant from ADR 0038. Its `output_validator` rejects
a response that does not return exactly one item per input entry, in order (`ModelRetry`,
mirroring `GlossaryTermTranslatorAgent`'s count-match validator, spec 0019 FR-4) — not a
text-fidelity check, since none applies here.

`SimplifiedDefinitionItemDto.definition_plain` is bounded by `Field(min_length=1,
max_length=400)` (added during grilling, 2026-09-25) — a mechanical backstop alongside
the prompt's own "1-2 frasi brevi" instruction, rejecting (`ModelRetry`, mirroring
`TranslatedTermItemDto._reject_blank`'s blank check) a response that drifts into a full
paragraph instead of a short plain-language rewrite. 400 characters is generous for two
short Italian sentences while still catching a genuinely runaway generation.

The agent's own YAML config (`configs/agents/glossary_definition_simplifier.yaml`) sets
`model_name: openrouter/google/gemini-2.5-flash-lite` (added during grilling,
2026-09-25 — the same model `glossary_term_translator.ru.yaml` already uses for its own
small, well-bounded batch task; simplification is a similarly narrow, per-entry
rewrite, not open-ended generation, so the lighter/cheaper sibling model is the right
default rather than the `-flash` tier `glossary_extractor.yaml` upgraded to) and
`max_tokens` explicitly, as every sibling agent config already does
(`glossary_term_translator.ru.yaml:4` sets `max_tokens: 800` for a much smaller
per-item payload — a bare term, not a sentence). Sized against
`GlossaryConfig.simplification_batch_size`'s default (10) and the 400-character cap
above (~100 tokens per Italian sentence at ~4 chars/token, so ~1000 tokens of pure
content for a full batch), doubled for JSON-structure and formatting overhead:
`max_tokens: 2000`. Both values remain tunable during implementation on real output,
like the exact prompt text (Open Questions).

This agent is invoked exclusively by `simplify-glossary-definitions` (FR-2), never by
`build-glossary` or `translate-glossary-terms`.

### FR-4: A failing batch fails itself, not its siblings

Mirrors spec 0019 FR-5/ADR 0039 exactly, at the batch level: a failing batch (including
an exhausted validator retry) is logged at `error` with the row ids it covers and
skipped; the remaining batches still run. After the last batch, if any batch failed,
the run raises `GlossaryDefinitionSimplificationError` listing them and exits non-zero.
Rows from failed batches keep `definition_plain = NULL` and are picked up automatically
by the next run's default (non-`--force`) selection.

### FR-5: Exactly one read-side call site switches to the plain text; everything else is unchanged

`ExplanationService._deduplicated_hints` (`services/explanation_service.py:270-277`) is
the **only** place this spec changes on the read side:

```python
CitedGlossaryTerm(
    term=candidate.term,
    definition=candidate.definition_plain or candidate.definition,
    term_ru=candidate.term_ru,
)
```

`candidate.definition_plain or candidate.definition` falls back to the verbatim text
when a row has not been simplified yet (or the simplifier returned only whitespace,
though the agent's own validator should prevent that) — a row is always a complete,
servable hint (FR-1), consistent with the `term_ru` precedent (spec 0019, ADR 0039).

Every other class in the read path is **unchanged**, by construction, not by
coincidence:

- `QuestionExplainerRequest.candidates_block` still reads `candidate.definition`
  (verbatim) — the model keeps grounding on the precise legal text (see rejected
  shapes).
- `CitedGlossaryTerm`, `CitedGlossaryTermResponse`, `ExplanationMapper`, and
  `guidami_ai_patente_bot`'s own `CitedGlossaryTerm` model gain no new field and no
  changed field: the wire contract of `GET .../explanation` does not change at all.
  `definition` in that response simply *contains* the plain text once one exists, by
  construction of FR-5's fallback expression — no client-visible schema change, no bot
  change.

### FR-6: The `GlossaryCandidate` model carries the new column through

`GlossaryCandidate` (`guidami_ai_patente/models/glossary_candidate.py`) gains
`definition_plain: str | None`, populated by `GlossaryReadRepository._row_to_candidate`
from a `g.definition_plain` column added to that repository's `_COLUMNS`/query
(`guidami_ai_patente/repositories/glossary_read_repository.py:13-14,88-98`). This is the
only schema change to that model and that repository.

## Non-Goals

- No change to `build-glossary`'s extraction, chunking, embedding, or ADR 0038's
  verbatim guarantee — `GlossaryExtractorAgent` and the extraction service are
  untouched. The one exception is `GlossaryEntryWriteRepository`'s upsert, which gains
  a one-line `definition_plain = NULL` reset alongside its existing `term_ru = NULL`
  reset (FR-1a) — a cache-invalidation touch, not a functional coupling: the write
  repository still never calls, imports, or knows about the new agent or script.
- No change to `translate-glossary-terms`, `GlossaryTermTranslatorAgent`, or `term_ru`.
- No change to `QuestionExplainerAgent`'s prompt, request, or response contract — it
  keeps reading verbatim `definition` via `candidates_block` (FR-5).
- No change to `CitedGlossaryTerm`, `CitedGlossaryTermResponse`, `ExplanationMapper`, or
  any bot-side model — no new field, no API contract change.
- No write-through, caching, or on-demand generation of `definition_plain` at request
  time — it is filled offline, exactly like `term_ru` (spec 0019, ADR 0039).
- No interaction with spec 0021 (on-demand glossary enrichment) beyond the ordering
  note in the header: this spec does not implement, block on, or require spec 0021.
- No translation to any language — this is a register change within Italian
  (legalese → plain), not translation (spec 0019's `term_ru` scope is untouched).

## Architectural Decisions

### AD-1: A third independent script, not a step inside `build-glossary`

Mirrors spec 0019's ADR 0039 (term translation) for exactly the same reason, one column
over: a simplification failure must never fail, retry, or skip an extraction — `build-
glossary`'s job is producing the verbatim `definition` and its embedding, which is what
retrieval actually depends on; `definition_plain` is a presentation-only derived value
nothing else in the system depends on. FR-1a's upsert reset does not weaken this
decision: resetting a column to `NULL` on conflict is data invalidation the write
repository already performs for `term_ru`, not a call into the simplification pipeline
— `build-glossary` still runs, succeeds, or fails without ever knowing
`GlossaryDefinitionSimplifierAgent` exists.

### AD-2: The verbatim column is never touched, in either direction

`definition` keeps meaning exactly what ADR 0038 says it means: text mechanically
verified to be a substring of the source block. `definition_plain` is additive, never a
replacement, and no code path ever reads `definition` *from* `definition_plain` or vice
versa except FR-5's one fallback expression, which reads, never writes, either column.

### AD-3: The new agent has no verbatim constraint — a deliberately different validator shape

`GlossaryExtractorAgent`'s `output_validator` (ADR 0038) exists to stop the model from
rewriting normative text. `GlossaryDefinitionSimplifierAgent`'s entire job is rewriting
it, in the other direction (into plain language) — the two agents' validators encode
opposite invariants by design, which is also why simplification could never be a second
field on `GlossaryExtractorAgent`'s own response (it would need to both forbid and
require rewriting on the same call).

### AD-4: Fallback-on-read over gating on write, mirroring `term_ru`'s precedent

Spec 0019 (ADR 0039) already established that a `glossary_entries` row is complete and
servable the moment `build-glossary` writes it, with a derived column (`term_ru`)
filled in independently and possibly never, without that ever making the row
unservable. `definition_plain` reuses the identical shape: `FR-5`'s `or` fallback,
not a `WHERE definition_plain IS NOT NULL` filter anywhere, and not a required
ordering between `build-glossary` and `simplify-glossary-definitions`.

## Data Model

```sql
-- db/migrations/0022_glossary_definition_plain.sql
ALTER TABLE glossary_entries ADD COLUMN IF NOT EXISTS definition_plain TEXT;
```

And the matching edit to `db/init.sql`'s existing `CREATE TABLE glossary_entries`
(`db/init.sql:234-253`), adding, alongside `definition`:

```sql
    -- Plain-language rendering of `definition`, filled independently by
    -- simplify-glossary-definitions (spec 0022). NULL until simplified; a row is a
    -- complete, servable glossary entry either way (AD-4) — the read side falls back
    -- to `definition` verbatim when this is NULL.
    definition_plain  TEXT,
```

No index, no `CHECK`, no `UNIQUE` participation — it plays no role in the table's
natural key or its embedding/full-text arms.

`GlossaryEntryEntity` (the write-side insertable projection, spec 0019) is **not**
changed: exactly like `term_ru`, this column is never part of the entity `build-
glossary` inserts/upserts through — it is written exclusively via
`GlossaryDefinitionUpdateRepository`'s own `UPDATE`.

## Package Structure

New files under `src/glossary/`, following the exact shape of the `term_ru` pipeline
(spec 0019) — file names chosen by direct analogy to their `*_term_*`/`*Term*`
counterparts:

```
src/glossary/
├── simplify_main.py                                  # entry point: simplify-glossary-definitions
├── agents/
│   └── glossary_definition_simplifier/
│       ├── glossary_definition_simplifier_agent.py    # GlossaryDefinitionSimplifierAgent (@agent)
│       └── dto/
│           ├── glossary_definition_simplifier_request.py   # DefinitionToSimplifyDto, ...Request
│           └── glossary_definition_simplifier_response.py  # SimplifiedDefinitionItemDto, ...Response
├── models/
│   ├── glossary_definition_row.py                     # GlossaryDefinitionRow (id, term, definition)
│   ├── simplified_definition.py                       # SimplifiedDefinition (id, definition_plain)
│   ├── glossary_definition_simplification_request.py  # GlossaryDefinitionSimplificationRequest (force)
│   └── glossary_definition_simplification_report.py   # ...Report (simplified, still_missing)
├── repositories/
│   ├── glossary_definition_read_repository.py         # (@repository) rows with definition_plain IS NULL
│   └── glossary_definition_update_repository.py       # (@repository) UPDATE definition_plain by id
├── services/
│   ├── glossary_definition_simplification_service.py     # (@service) batch → agent, no DB access
│   └── glossary_definition_simplification_run_service.py # (@service) sequences the script (AsyncUseCase)
└── exceptions/
    └── glossary_errors.py                              # + GlossaryDefinitionSimplificationError
```

| Piece | Role |
|---|---|
| `GlossaryDefinitionSimplifierAgent` | `BaseAgent`, `@agent`, mirrors `GlossaryTermTranslatorAgent`'s shape (autowired `GlossaryAgentConfigRepository`/`Provider[AsyncOpenAI]`/`LlmCallTracker`, a constructor accepting test overrides, one `output_validator` for count-match). |
| `GlossaryDefinitionSimplificationService` | `AsyncUseCase[Sequence[GlossaryDefinitionRow], list[SimplifiedDefinition]]`, `@service`. Runs the agent over one batch; never touches the database — mirrors `GlossaryTermTranslationService`. |
| `GlossaryDefinitionSimplificationRunService` | `AsyncUseCase[GlossaryDefinitionSimplificationRequest, GlossaryDefinitionSimplificationReport]`, `@service`. Sequences `simplify-glossary-definitions`: read missing rows, batch, simplify, write back, isolate per-batch failures (FR-4) — mirrors `GlossaryTermTranslationRunService`. Invoked via `__call__`. |
| `GlossaryDefinitionReadRepository` / `GlossaryDefinitionUpdateRepository` | `@repository`, one query shape each, mirroring `GlossaryTermReadRepository`/`GlossaryTermUpdateRepository` (including their `table_name`/`client` test-override constructor parameters). |
| `simplify_main.py` | Composition root, mirrors `translate_main.py`: loads `GlossaryConfig`/`OpenRouterConfig`/`ObservabilityConfig`, builds `commons` primitives via the existing `wiring.py`, registers them, resolves and runs `GlossaryDefinitionSimplificationRunService`. |

`GlossaryConfig` (`configs/glossary_config.py`) gains
`simplification_batch_size: int = Field(default=10, ge=1)`, alongside the existing
`translation_batch_size`.

## Constraints

- No import from `guidami_ai_patente_ingestor`, `labeling`, `guidami_ai_patente`, or the
  bot — only `commons` and `domain` (unchanged from spec 0019's AD-1).
- pywire field injection for every new agent/service/repository (`.claude/rules/pywire-di.md`,
  AD-1a of spec 0019): `Autowired[T]` class fields, no constructor-parameter DI for them.
- Config loaded at the entry point (`simplify_main.py`), never inside builders/services.
- `AsyncUseCase`s invoked via `__call__` (`.claude/rules/use-case-invocation.md`);
  classes under `services/` carry a role suffix (`.claude/rules/code-conventions.md`).
- One class per file; no `continue` in loops; lazy `%s`/`%r` logging with levels used
  purposefully (`.claude/rules/logging.md`).
- Agent config file unsuffixed (Italian, base language, `.claude/rules/agent-config-naming.md`).
- Agent response DTO (`SimplifiedDefinitionItemDto`/`GlossaryDefinitionSimplifierResponse`)
  docstring and `Field(description=...)` in Italian, per the agent-response-DTO exception
  in `.claude/rules/code-conventions.md`; the request DTO stays English.
- The new script is registered under `[project.scripts]` in `pyproject.toml`, alongside
  `build-glossary`/`translate-glossary-terms` (`pyproject.toml:38,43`).
- Tests live in `tests/glossary/` mirroring `src/glossary/`, no `__init__.py`, pytest, TDD.
- `guidami_ai_patente`-side changes (`GlossaryCandidate`, `GlossaryReadRepository`,
  `ExplanationService._deduplicated_hints`) follow that package's own pywire/testing
  conventions unchanged — no new convention introduced there.

## Testing

- **Simplifier validator** (unit): a batch response with fewer/more items than the
  input batch is rejected (`ModelRetry`); a matching-count response is accepted; an
  item over `max_length=400` or blank is rejected by `SimplifiedDefinitionItemDto`'s
  own field validation (mirroring `TranslatedTermItemDto`'s tests).
- **Write repository reset** (`@pytest.mark.integration`, regression + new behavior):
  re-upserting an existing `(source, article_number, comma_number, term)` row whose
  `definition_plain` was already set resets it to `NULL` on conflict, exactly like the
  existing `term_ru` reset this test extends.
- **Simplification service** (unit, fake agent): one batch in, one `SimplifiedDefinition`
  per row out, aligned 1:1 by position (`zip(..., strict=True)`).
- **Definition read repository** (unit, fixture rows): selects only rows with
  `definition_plain IS NULL`; with `--force`, selects every row regardless of its
  current `definition_plain`.
- **Definition update repository** (`@pytest.mark.integration`): updates
  `definition_plain` for the given id only; every other column (`definition`, `term`,
  `term_ru`, `embedding_3_small`, ...) is unchanged.
- **Run service** (unit, fakes): a failing batch is logged and skipped, the remaining
  batches still run, and the run raises `GlossaryDefinitionSimplificationError` listing
  the failed ones; a rerun with no `--force` only ever selects rows still
  `definition_plain IS NULL`.
- **Entry point**: `simplify-glossary-definitions --dry-run` writes nothing, opens no
  connection, makes no LLM call.
- **`GlossaryReadRepository`** (`@pytest.mark.integration`): a row's `definition_plain`
  round-trips through `_row_to_candidate` onto `GlossaryCandidate.definition_plain`,
  including the `NULL` case.
- **`ExplanationService._deduplicated_hints`** (unit, fakes — regression + new
  behavior): a candidate with a non-`NULL` `definition_plain` produces a
  `CitedGlossaryTerm.definition` equal to it, not to the verbatim `definition`; a
  candidate with `definition_plain = None` falls back to the verbatim `definition`
  (today's unchanged behavior for every row not yet simplified).
- **Regression guard**: `QuestionExplainerRequest.candidates_block`'s existing tests
  keep asserting it renders `candidate.definition` (verbatim), confirming this spec did
  not redirect the grounding prompt.

## Feasibility Evidence

Verified 2026-09-25 on branch `feat/backend`.

- **Problem** — `services/explanation_service.py:270-277` (`_deduplicated_hints` copying
  verbatim `candidate.definition` onto `CitedGlossaryTerm`);
  `api/schemas/quiz_explanation.py:38-49` (`CitedGlossaryTermResponse`'s docstring
  stating it "is rendered by the bot as its own glossary-block line").
- **FR-1/Data Model** — `db/init.sql:234-253` (current `glossary_entries` DDL, `term_ru`'s
  existing nullable/no-`CHECK` shape as the precedent this column copies);
  `db/migrations/0020_glossary_term_ru_nullable.sql` (the migration-naming/shape precedent).
- **FR-1a** (added during grilling, 2026-09-25) —
  `src/glossary/repositories/glossary_entry_write_repository.py:47-58` (`_upsert`'s
  `ON CONFLICT ... DO UPDATE SET ..., term_ru = NULL` — confirmed the existing,
  unconditional reset this spec's `definition_plain = NULL` addition mirrors exactly).
- **FR-2/FR-3/FR-4/Package Structure** — direct reads of
  `src/glossary/repositories/glossary_term_read_repository.py`,
  `glossary_term_update_repository.py`,
  `src/glossary/models/glossary_term_row.py`,
  `glossary_term_translation_request.py`, `glossary_term_translation_report.py`,
  `src/glossary/services/glossary_term_translation_run_service.py`,
  `src/glossary/translate_main.py`,
  `src/glossary/agents/glossary_term_translator/glossary_term_translator_agent.py` and
  its `dto/` files, `src/glossary/exceptions/glossary_errors.py` — every new class in
  this spec's Package Structure mirrors one of these files' shape directly.
- **FR-5/FR-6** — `guidami_ai_patente/repositories/glossary_read_repository.py:13-14,
  60-98` (`_COLUMNS`, `candidates_for`, `_row_to_candidate` — confirmed `definition` is
  the only text column read today besides `term`/`term_ru`);
  `guidami_ai_patente/models/glossary_candidate.py` (current fields, no `definition_plain`
  yet); `guidami_ai_patente/agents/question_explainer/dto/question_explainer_request.py:39-50`
  (`candidates_block` reads `candidate.definition`, confirmed unchanged by this spec);
  `guidami_ai_patente/models/cited_glossary_term.py`,
  `guidami_ai_patente/api/schemas/quiz_explanation.py:38-53` (both confirmed to need no
  field addition — `definition`'s *value*, not its field, changes).
- **AD-1/AD-4** — `docs/second-brain/adr/0039-glossary-term-translation-fully-decoupled-script.md`
  (the decoupling precedent this spec's AD-1 mirrors for a second derived column).
- **Constraints** — `pyproject.toml:31-43` (`[project.scripts]`, existing
  `build-glossary`/`translate-glossary-terms` entries); `src/glossary/configs/glossary_config.py:79`
  (`translation_batch_size`, the field this spec's `simplification_batch_size` mirrors).
- **Coordinates with (spec 0021)** —
  `docs/superpowers/specs/2026-09-25-on-demand-glossary-enrichment-design.md` (status
  draft, pending sign-off as of this spec's writing — confirmed not yet implemented, so
  this spec's changes to `GlossaryCandidate`/`_deduplicated_hints` land first, per the
  user's explicit direction).

## Open Questions

- [ ] **non-blocking** — Exact prompt text for `GlossaryDefinitionSimplifierAgent`
  (register, sentence count, whether to name the concept being defined at the start of
  the sentence) — left to implementation, tuned on real output. Model
  (`openrouter/google/gemini-2.5-flash-lite`), `max_tokens` (2000) and the
  `definition_plain` length bound (`max_length=400`) were resolved during grilling
  (2026-09-25) — see FR-3 — but remain tunable if real output shows the bounds are
  wrong in either direction.

## Follow-ups after implementation

- Run `second-brain:update` (`database.md`, `architecture.md`, `patterns.md`) to record
  the new column, the third script, and the fallback-on-read pattern.
- Record an ADR (`second-brain:adr`) for: a third independent, decoupled script mirroring
  `term_ru`'s precedent for a second derived column, and fallback-on-read over
  gating-on-write for a not-yet-filled derived column.
- Update the `CLAUDE.md` scripts table with `simplify-glossary-definitions`.
- When spec 0021 is implemented, its author must re-read this spec's FR-5/FR-6 changes
  to `GlossaryCandidate`/`_deduplicated_hints` before touching either class again.

## Sign-off

- **Scope approved by user:** pending — spec written 2026-09-25 from an interactive
  `superpowers:brainstorming` session; awaiting the user's review of this file.
- **Feasibility asserted:** by the assistant on 2026-09-25, based on the Feasibility
  Evidence above (direct source reads of the `term_ru` pipeline this spec mirrors).
- **Definition of Done verified:** not yet — pending implementation.

## Changelog

- **2026-09-25 (later)** — Grilling round (`mattpocock-skills:grilling`, one question at
  a time per this project's CLAUDE.md override). Found and closed a real staleness gap:
  `GlossaryEntryWriteRepository`'s upsert already resets `term_ru = NULL` on every
  conflict but had no equivalent for `definition_plain`, so a `--force` rebuild
  changing a block's verbatim text would silently orphan the old plain-language
  rendering forever — added FR-1a to reset it too, and corrected the Non-Goals bullet
  that had claimed `GlossaryEntryWriteRepository` stays fully untouched. Added a
  mechanical `max_length=400` bound to `SimplifiedDefinitionItemDto.definition_plain`
  (previously left fully open) and fixed the agent's model
  (`openrouter/google/gemini-2.5-flash-lite`, matching `glossary_term_translator.ru`'s
  choice for a similarly narrow per-entry task) and `max_tokens` (2000, sized against
  the batch size default and the new length bound) — both requested directly by the
  user rather than surfaced as open questions.
- **2026-09-25** — Initial draft, from an interactive `superpowers:brainstorming`
  session (schema direction, consumer scope, NULL fallback, and pipeline shape all
  decided conversationally, one question at a time, per this project's CLAUDE.md
  override of brainstorming's default batching). The requester's own first proposal
  (swap `definition`'s semantics, add `definition_extracted` for the verbatim text) was
  traced against real consumers and superseded by the opposite shape (leave `definition`
  untouched, add `definition_plain`) once it became clear both shapes equally satisfy
  the "consumers don't change" goal, but only one avoids touching the write path/
  embedding spec 0019 already validated (ADR 0038). Numbered 0022 (0021 already taken
  by the unrelated, still-pending on-demand-enrichment spec found during this session);
  the requester confirmed this spec is implemented before spec 0021, regardless of
  numbering order.
