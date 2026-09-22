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

# Spec 0019: Definition glossary, built once by a standalone package

| | |
|---|---|
| **Id** | 0019 |
| **Status** | draft |
| **Date** | 2026-09-21 |
| **Discussion log** | — (brainstormed inline via `superpowers:brainstorming`, then stress-tested via `mattpocock-skills:grilling`; no separate transcript file) |
| **Supersedes / superseded by** | — |
| **Read by** | Spec 0020 (question and answer explanation): its retrieval queries this table, but does not require it to be populated — see Independence from Spec 0020 |

## Problem & Motivation

Spec 0020 explains a quiz question and grounds unfamiliar terms of art
("carreggiata", "banchina") on official definitions. Those definitions exist in the
corpus, but not in a usable shape:

- CdS art. 3 comma 1 is **one** ~11,300-character string holding ~65 definitions, stored
  as one row with one vector (`knowledge_flows.py:149-160`; no chunking exists), so no
  per-term retrieval is possible over it. Art. 2, 151, 157 and the CAP definitions
  article have the same shape, in four different textual formats.
- Passing those articles whole in every explanation prompt costs ≈ 6k tokens (≈ 16k with
  CAP art. 1) for a single answer.
- **CAP art. 1 is not in the indexed corpus at all**: the `cap` source is
  `codice_rca.json` (96 articles, filtered by `rca_ranges`), and `data/cleaned/cap`
  contains no article titled "Definizioni". Any design that reads definitions from the
  corpus database would silently lack the largest definitions article.

This spec builds, **once**, a glossary of official definitions as its own table: one row
per term, with its Italian definition, an embedding and a full-text index, produced by a
**standalone batch package**, `src/glossary/`, with its own agent, data model,
repositories and service — the ingestor and its CLI are not touched. It concerns no quiz
question and no user, and it holds no translation: the term this glossary anchors is
Italian, the project's base language; a non-Italian rendering is produced once, on
demand, over the *final* explanation text that consumes it, by the existing translator
(spec 0018) — not stored per glossary entry.

Shapes considered and rejected, recorded so a future reader does not re-propose them:

- **New `ingest prepare|index|reset glossary` entities** — rejected: the glossary is a
  self-contained derived asset, and hosting it in the ingestor would couple it to the
  ingestor's CLI, its config root (`IngestorConfig`), its layer/status/reset machinery
  and its `--dry-run`/manifest conventions, all built for the corpus and quiz
  lifecycles. The repository already has the right precedent: standalone packages with
  their own script (`labeling`, `retrieval_evaluation`, `test_data_sampler`).
- **Whole definition articles in every prompt** — rejected: ~6-16k tokens per
  generation. The real reason is grounding reliability and one place to review a
  definition, not raw dollar cost (order of $10-15 total at Flash-class pricing for a
  full pass, not verified against `llm_call_logs.cost_usd`).
- **Splitting the definitions articles into one comma per term inside `articles` /
  `article_commas`** — rejected: it changes the shared corpus, altering the labeling
  candidate set and therefore the meaning of the epoch and of every golden set already
  computed, for a feature that does not concern them.
- **Reading the definition text from the corpus database** — rejected: CAP art. 1 is
  not there (see above), and it would tie this glossary to corpus ingestion order.
- **Deterministic parsers, one per format** — rejected: four fragile parsers over
  scraped text (nested `7-bis`, repealed entries), and CdS art. 157 has no term marker
  ("per arresto si intende…").
- **A hand-curated file** — rejected: ~250 entries to write and keep aligned by hand,
  with no guarantee they stay faithful to the scraped text.
- **A committed per-block JSON file as a review layer** (extract → file → embed →
  index) — deferred for simplicity, as requested: the pipeline writes straight to the
  database. Consequence, accepted: a correction to a definition is a SQL `UPDATE`,
  unversioned, and is overwritten if that block is rebuilt with `--force` (see Open
  Questions).
- **Storing a full Russian translation (definition, summary) per glossary entry** —
  rejected: the entry that consumes this glossary (`QuestionExplainerAgent`, spec 0020)
  writes Italian, merged with the existing answer explanation into one message, and
  that whole message is translated once, on demand, by the existing
  `ExplanationTranslatorAgent` (spec 0018). A full Russian definition or summary would
  never be read by anything — only the *term itself* needs a pre-agreed rendering (see
  FR-4/AD-3, reinstated after the requester asked whether the translate endpoint could
  take translation hints), not its definition. This still drops two of the three
  columns and the per-entry batching from this spec's first draft.
- **Extracting also the *non-official* terms** (from the quiz itself, e.g. "precedenza",
  "svolta") into the glossary — deferred: a second, larger pipeline (extraction over
  7106 questions, dedup, review) that this spec does not need. Spec 0020 covers those
  terms with a model-generated fallback, explicitly not grounded on this glossary.

## Functional Requirements

### FR-1: Definition blocks are configured, and read from the parsed layer

`GlossaryConfig.blocks` (frozen `GlossaryBlockConfig`) lists what to extract:
`source`, `file`, `article_number`, and an optional `comma_number` (absent → every comma
of the article). Initial set:

| Block | Source file | Comma | ≈ size |
|---|---|---|---|
| CdS art. 2 (road classification) | `cds/codice_della_strada.json` | all | 7.7k chars |
| CdS art. 3 (road and traffic definitions) | `cds/codice_della_strada.json` | 1 | 11.3k |
| CdS art. 151 (light-signal definitions) | `cds/codice_della_strada.json` | 1 | 3.6k |
| CdS art. 157 (arresto, fermata, sosta) | `cds/codice_della_strada.json` | 1 | 0.9k |
| CAP art. 1 (insurance definitions) | `cap/codice_assicurazioni_private.json` | 1 | ~34k |

Files are read from `GlossaryConfig.parsed_dir` (default `data/parsed`), **never** from
the database and never from the RCA-filtered `codice_rca.json`. The block text is the
concatenation of the selected commas with the parser's inline `((…))` markup removed
(the same rule as the ingestor's cleaner, reimplemented in this package — see AD-8).

### FR-2: `uv run build-glossary [--force] [--dry-run]`

One new script, `build-glossary = "glossary.main:main"` under `[project.scripts]`. For
each configured block, in order: read its text (FR-1), skip it if the table already
holds entries for it and `--force` was not passed, otherwise extract (FR-3), embed and
write (FR-4).

- `--dry-run` prints the blocks and the step chain that would run and exits: no
  filesystem write, no LLM call, no database connection.
- Every real run logs to the console and to `logs/build_glossary_<timestamp>/run.log`
  (via the existing `RunArtifactWriter`, as `label-golden-set` does).
- It ends with a per-block summary (entries written, or skipped) printed to stdout.
- Nothing is added to `ingest`: no entity under `prepare`/`index`/`reset`, no `status`
  integration.

### FR-3: Extraction with a verbatim guarantee

`GlossaryExtractorAgent` (`configs/agents/glossary_extractor.yaml`, Italian, and
unsuffixed: it is the base language, not a target language — see
`.claude/rules/agent-config-naming.md`) receives one block's text (chunked between
entries when it exceeds `GlossaryConfig.max_block_chars`) and returns
`list[{term, definition}]`, skipping repealed entries. Its `output_validator` raises
`ModelRetry` (message in Italian) when:

- a `definition` is not, after whitespace normalization, a substring of the block text;
- a `term` is empty or does not occur in the block text;
- two entries share the same `term`.

The model can therefore select and split, never rewrite, the normative text.

### FR-4: The term (not the definition) is translated once, as a future hint

`GlossaryTermTranslatorAgent` (`configs/agents/glossary_term_translator.ru.yaml`,
language-suffixed per `.claude/rules/agent-config-naming.md`: unlike the extractor, its
whole job is producing a Russian rendering) receives entries in batches
(`GlossaryConfig.translation_batch_size`) and returns, per entry, `term_ru`: the
official Russian road-traffic term (`max_length=80`). Nothing else is translated — no
definition, no summary. A batch response that does not return exactly one item per
input entry, in order, is rejected (`ModelRetry`).

`term_ru` is stored for exactly one purpose: to be handed to
`POST /explanations/translate` as a translation hint (spec 0018, FR-8/AD-9, amended for
this spec) when spec 0020 assembles its final, translatable explanation text. It is
never returned by any API response field of its own, and this spec builds no
consumer for it — that is spec 0020's job.

### FR-5: Embed and write, idempotently

Each entry is embedded as `f"{term}\n{definition}"` through the existing `commons`
`EmbeddingService` (`text-embedding-3-small`, stored in `embedding_3_small`), then
written by `GlossaryEntryWriteRepository`: **upsert** by the natural key first, then
**delete** the block's entries that no longer appear, scoped to that block (the
reconciliation pattern of spec 0010). The order matters: a failure between the two
statements leaves at worst a few stale extra rows, never an empty block, and a rerun
converges.

### FR-6: A failing block fails the run, not its siblings

A block whose extraction, embedding or write fails (including an exhausted validator
retry) is logged at `error` with its id and skipped; the remaining blocks still run.
After the last block, if any block failed, the run raises `GlossaryBuildError` listing
them and exits non-zero. Blocks already written stay written.

### FR-7: The table

`glossary_entries` (Data Model): Italian term and definition, the term's Russian
rendering (FR-4), provenance columns (`source`, `article_number`, `comma_number`), an
`embedding_3_small` column and a generated full-text column on the term. No foreign key
to `articles` or to any quiz table (AD-3).

### FR-8: The whole pipeline is cheap and bounded

One extraction call per block chunk, plus one translation call per
`translation_batch_size` terms: on the order of a few dozen calls total for the initial
set (~250 terms). Blocks run sequentially; there is no concurrency knob (YAGNI at this
size).

## Independence from Spec 0020

This package can be implemented, and its script run, entirely independently of spec
0020's backend/bot work, in either order:

- **This spec first**: spec 0020's retrieval reads a populated table from day one.
- **Spec 0020 first**: its own implementation plan creates the `glossary_entries` table
  in `db/init.sql` (empty; no rows), so its retrieval queries a real, empty table rather
  than failing on a missing relation (an empty result is an explicitly valid case for
  it — spec 0020, FR-3). This spec's Data Model (below) is authoritative for that DDL:
  if spec 0020's plan lands the table first, this spec's plan finds it already present
  and does not redefine it, only populates it.

Either way, only **one** plan actually writes the `CREATE TABLE` — the two plans must
not both attempt it independently without checking `db/init.sql` first.

## Non-Goals

- No runtime code: no endpoint, no retrieval query used by the API, no agent used by the
  API — retrieval is spec 0020's job, over the table this spec fills.
- No change to the ingestor: no new command, no new config field, no import from it.
- No `ingest reset` or `ingest status` integration for this table. To wipe it, rebuild
  with `--force`, or `TRUNCATE glossary_entries` by hand.
- No translation of the definition or a summary — only the bare term is translated
  (FR-4); no language other than Russian, matching spec 0018's own YAGNI scope (see
  Rejected shapes).
- No non-official terms (extraction from the quiz), no glossary editing UI, no review
  file layer (see Rejected shapes).
- No change to `articles`, `article_commas`, the labeling candidate set, the epoch, or
  any golden set.
- No vector index on `glossary_entries`: at ~250 rows a sequential scan is exact and
  faster than an index.

## Package Structure

A top-level package `src/glossary/`, modelled on `src/labeling/`'s layout but wired with
**pywire** field injection (`.claude/rules/pywire-di.md`), a deliberate, narrow exception
to that rule's batch/one-shot default — see AD-1a.

```
src/glossary/
├── main.py                       # entry point: `build-glossary`; the composition root
├── wiring.py                     # builds the few commons primitives pywire can't:
│                                  #   PostgresClient, EmbeddingService, OpenRouter provider
├── configs/
│   └── glossary_config.py        # GlossaryConfig, GlossaryBlockConfig (frozen) — data, not
│                                  #   a component; registered via register_instance (AD-1a)
├── agents/
│   ├── glossary_extractor/           # GlossaryExtractorAgent (@agent) + dto/
│   └── glossary_term_translator/     # GlossaryTermTranslatorAgent (@agent) + dto/
├── models/                       # GlossaryBlock, ExtractedEntry, TranslatedTerm, BlockOutcome
├── mappers/                      # GlossaryEntryMapper: extracted + translated + vector → entity
├── repositories/
│   ├── glossary_block_read_repository.py   # (@repository) parsed article file → block text
│   ├── glossary_entry_read_repository.py   # (@repository) DB: does this block already have entries?
│   └── glossary_entry_write_repository.py  # (@repository) DB: upsert + scoped reconciliation
├── services/
│   ├── glossary_extraction_service.py      # (@service) block text → extracted entries
│   ├── glossary_term_translation_service.py  # (@service) extracted entries → term_ru, batched
│   └── glossary_build_service.py           # (@service) sequences the steps, block by block
└── exceptions/                   # GlossaryBuildError
```

Every class above except `configs/` declares its collaborators as `Autowired[T]` class
fields — no constructor-parameter DI for them, per `pywire-di.md`'s "Convention" section,
applied here exactly as it is in `guidami_ai_patente`.

| Piece | Role |
|---|---|
| `GlossaryBuildService` | An `AsyncUseCase[GlossaryBuildRequest, GlossaryBuildReport]` `@service` (request: `force`; report: one `BlockOutcome` per block), like `GoldenSetLabelingService` — sequencing lives in a service here, as in `labeling`, rather than in an `orchestrators/` package. Invoked via `__call__` (`use-case-invocation.md`). |
| `GlossaryExtractionService` | One responsibility: run the extractor agent over one block's text with chunking and return typed entries. `@service`, `AsyncUseCase`. |
| `GlossaryTermTranslationService` | One responsibility: run the term translator agent over extracted entries in batches and return each entry's `term_ru`. `@service`, `AsyncUseCase`. |
| Read repositories | `@repository`. The block source (files) and the "already built?" check (DB) are two different stores, hence two read repositories. |
| Write repository | `@repository`. The only class that writes `glossary_entries`. |
| `main.py` | Loads `GlossaryConfig`, `OpenRouterConfig` and `ObservabilityConfig` **once, here** (`rules/python/architecture.md`); builds the handful of `commons` primitives pywire cannot construct itself (`wiring.py`) and registers them with `register_instance`; then `container.resolve(GlossaryBuildService)` and runs it. No `pywire.fastapi`, no lifespan — `container.close()` at the end fires any `@pre_destroy` hook (e.g. closing the Postgres pool). |

The insertable row is `GlossaryEntryEntity` in `src/domain/entities/glossary/` (shared
shape: spec 0020's API reads the same table), named per the entity convention.

## Architectural Decisions

### AD-1: A standalone package, not an ingestor entity

See the first rejected shape. The package depends only on `commons` and `domain`, never
on `guidami_ai_patente_ingestor`, `labeling` or `guidami_ai_patente`.

### AD-1a: pywire, as a narrow exception to the batch-package default

`.claude/rules/pywire-di.md` scopes pywire to `guidami_ai_patente` and the bot by
default, keeping `labeling`/`retrieval_evaluation`/the ingestor on manual constructor
injection — a convention choice for those *existing* packages, not a technical
limitation (the container has no FastAPI dependency of its own). `glossary` opts in
because (a) its own agent/service/repository graph benefits from field injection the
same way the API's does — mirroring `ExplanationTranslatorAgent`'s three-`Autowired`
shape almost verbatim — and (b) it never imports, and is never imported by, `labeling`
or `retrieval_evaluation`, so there is no shared-default-container collision risk to
design around (contrast the bot/API `QuizApiClient` case in `pywire-di.md`). This is a
decision about `glossary` specifically, recorded in the rule file; it does not imply
`labeling`/`retrieval_evaluation`/the ingestor should be migrated too — that is a
separate, larger decision the user has explicitly not made here.

`GlossaryConfig` is data, not a component, exactly like `AppConfig`: loaded once in
`main.py` and handed to the container via `register_instance`, never autowired as if
it built itself. The same treatment applies to the few `commons` primitives pywire has
no constructor recipe for (`PostgresClient`, `EmbeddingService`, the OpenRouter
provider) — `wiring.py` builds them, `main.py` registers the built instances, and every
`glossary`-owned `@agent`/`@service`/`@repository` autowires them like any other
dependency.

### AD-2: LLM extraction guarded by a mechanical verbatim check

Chosen over parsers and a hand-curated file (Problem & Motivation). The `output_validator`
(FR-3) turns "the model must not rewrite the law" into a check, following the precedent of
`CommaLabelerAgent`'s ordinal validator (spec 0014): a mechanically checkable invariant is
enforced in code, not in the prompt.

### AD-3: Provenance without foreign keys

`(source, article_number, comma_number)` are plain text columns. `ingest reset knowledge`
truncates `articles`, and this glossary is deliberately independent of that lifecycle
(it is built from parsed files, FR-1), so a foreign key would couple two things that must
not be coupled. Consequence: no FK, hence no `TRUNCATE`-list churn in the integration
fixtures.

### AD-4: The embedding column follows the model-column convention

`embedding_3_small VECTOR(1536)`, exactly as `quiz_question_embeddings` (spec 0008,
AD-6): the model is encoded in the column name because pgvector fixes the dimension in
the type; a new model is a new `embedding_*` column, with the `CHECK (num_nonnulls(...)
> 0)` extended alongside. Full-text search is a generated `tsv_term` (band A, Italian
configuration) with a GIN index, like `tsv_text`/`tsv_title` in `db/init.sql`, but on the
**term only**: an entry is a candidate when the question uses the term; indexing the
definition text too would match on every common word in it. The dense arm (spec 0020)
embeds term plus definition, so semantic proximity is still covered.

### AD-5: Its own configuration root

`GlossaryConfig(BaseConfig)` with `configs/glossary.yaml`, `frozen=True`, holding
`postgres: PostgresConnectionConfig` (secrets from `.env`, as `AppConfig`), `agents_dir`
(validation alias `AGENTS_DIR`, **no default**, so a missing value is a loud
`ValidationError`), `parsed_dir`, `blocks`, `max_block_chars`, `translation_batch_size`,
the embedding settings and `glossary_entries_table`. It is a third `agents_dir` root
reading the same env var;
this prompt enters no epoch (the epoch belongs to the judge, ADR 0020), so nothing
depends on it matching the others — only on being set. It is **not** nested in
`IngestorConfig`, unlike `LabelingConfig`, which is exactly the coupling this spec
avoids.

### AD-6: Straight to the database

The pipeline reads parsed files and writes the table; it keeps no intermediate artifact
(Rejected shapes). Idempotency comes from the natural key and from skip-unless-`--force`.

### AD-7: One table, read by two independent producers/consumers

This package is the only writer of `glossary_entries`. Spec 0020's `GlossaryReadRepository`
(a different package, `guidami_ai_patente`) is a reader only. Both packages happen to use
pywire (AD-1a), but as two entirely separate containers/processes — a batch script and a
FastAPI app — never the same one; neither package imports the other, and they meet only
at the table, exactly as `guidami_ai_patente` and `guidami_ai_patente_ingestor` already
meet at `quiz_questions`.

### AD-8: A small deliberate duplication instead of an ingestor import

`ArticleCleanerService` (`_INLINE_MARKUP_PATTERN = r"\(\((.*?)\)\)"`) works on the
ingestor's `ParsedArticleModel`; importing it would make this package depend on the
ingestor. The glossary needs only the comma texts, so it reads them with its own minimal
model and strips the same inline markup itself (a few lines). If the cleaning rule ever
changes, this copy is the one to update — the accepted price of independence.

### AD-9: Term translation is a second, minimal agent, kept out of extraction

`GlossaryTermTranslatorAgent` is a separate agent from `GlossaryExtractorAgent`, not a
second field on the extractor's response, for three reasons: the two tasks have
different validators (verbatim-substring for extraction, free but bounded for
translation — Russian's grammar means the "same word" check spec 0019's extractor
validator applies to Italian cannot apply to `term_ru`); different failure semantics
(a translation failure should not discard an otherwise-valid extraction, since the
definition and its embedding do not need `term_ru` at all — only spec 0020's hint
mechanism does); and different batching (extraction runs once per block, chunked by
size; translation runs once per `translation_batch_size` terms, chunked by count).
`term_ru` is stored on the same row as its Italian term (not a child table) because,
per the reasoning that dropped the fuller Russian translation, only Russian exists
today (YAGNI, mirrors spec 0018) — a second language would revisit this.

## Data Model

New table in `db/init.sql` (a schema change: the dev DB must be recreated, per
`CLAUDE.md`). **Authoritative here** regardless of which plan (this spec's or spec
0020's) lands it first — see Independence from Spec 0020.

```sql
CREATE TABLE IF NOT EXISTS glossary_entries (
    id                BIGSERIAL PRIMARY KEY,
    source            TEXT NOT NULL,
    article_number    TEXT NOT NULL,
    comma_number      TEXT NOT NULL,
    term              TEXT NOT NULL,
    definition        TEXT NOT NULL,
    -- Consumed only as a spec 0020 translation hint (POST /explanations/translate,
    -- spec 0018 FR-8) — never returned by any API response field of its own (FR-4).
    term_ru           TEXT NOT NULL,
    embedding_3_small VECTOR(1536),
    -- Generated, never written by application code (same convention as
    -- articles.tsv_title); band A because only the term is indexed (AD-4).
    tsv_term          TSVECTOR GENERATED ALWAYS AS
                          (setweight(to_tsvector('italian', term), 'A')) STORED,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, article_number, comma_number, term),
    CONSTRAINT glossary_entries_at_least_one_vector
        CHECK (num_nonnulls(embedding_3_small) > 0)
);

CREATE INDEX IF NOT EXISTS idx_glossary_entries_tsv_term
    ON glossary_entries USING GIN (tsv_term);
```

`GlossaryEntryEntity` models the insertable projection (all columns except `id`,
`tsv_term`, `created_at`). The `comma_number` of a block that spans every comma of an
article is stored per entry as the comma the entry came from.

## Constraints

- No import from `guidami_ai_patente_ingestor`, `labeling`, `guidami_ai_patente` or the
  bot (AD-1); only `commons` and `domain`.
- pywire field injection for every agent/service/repository (AD-1a,
  `.claude/rules/pywire-di.md`): `Autowired[T]` class fields, no constructor-parameter
  DI for them. `GlossaryConfig` and manually-built `commons` primitives are registered
  via `register_instance`, exactly like `AppConfig` in `guidami_ai_patente`.
- Config loaded at the entry point, never inside builders or services.
- Every `UseCase`/`AsyncUseCase` invoked via `__call__` (`use-case-invocation.md`);
  classes under `services/` carry a role suffix (`code-conventions.md`).
- One class per file; enums in `enums/`; no `continue` in loops; lazy `%s` logging with
  levels used purposefully; `Generator[Y]` for `@contextmanager` return types.
- The new script is registered under `[project.scripts]` in `pyproject.toml`.
- Tests live in `tests/glossary/` mirroring `src/glossary/`, no `__init__.py`, pytest,
  TDD.

## Testing

- **Extractor validator** (unit): rejects a non-verbatim definition, an absent term and a
  duplicate term; accepts a valid response
  (`test_validator_rejects_definition_not_in_block`).
- **Extraction service** (unit, fake agent): a block over `max_block_chars` is chunked
  between entries and the chunks' results are concatenated.
- **Term translator** (unit, fake agent): a batch returning the wrong number of items is
  rejected; `term_ru` bound (`max_length=80`).
- **Block read repository** (unit, fixture file): selects the configured commas, strips
  `((…))` markup, and raises a clear error for an unknown article or comma.
- **Build service** (unit, fakes): a stored block is skipped without `--force`, rebuilt
  with it; a failing block does not stop its siblings and the run raises
  `GlossaryBuildError` listing it. Fakes are substituted via
  `container.register_instance(fake, as_type=RealType)` before `container.resolve(...)`,
  with `container.clear_instances()` between tests — the same pattern
  `pywire-di.md`'s "Testing with a substitute dependency" section documents for
  `guidami_ai_patente`, applied here per AD-1a.
- **Write repository** (`@pytest.mark.integration`): upsert by natural key; scoped
  reconciliation deletes only that block's stale entries; a failure between upsert and
  delete leaves the block non-empty; `embedding_3_small` accepts a 1536-dimension
  vector; `tsv_term` matches an inflected form of the term (`carreggiate` finds
  `CARREGGIATA`).
- **Entry point**: `--dry-run` writes nothing, opens no connection and makes no LLM call.
- A real-LLM `@pytest.mark.integration` spike over one small block (CdS art. 157) to
  validate extraction quality before the full run.

## Feasibility Evidence

Verified 2026-09-21/22 on branch `feat/backend`.

- **Problem** — art. 3 has 2 commas; comma 1 is 11,274 chars holding ~65 definitions
  inline (`data/parsed/cds/codice_della_strada.json`, article `3`); one embeddable row
  per comma, no chunking (`ingestor/orchestrators/knowledge_flows.py:149-160`,
  `mappers/article_mapper.py:49-78`).
- **FR-1** — `configs/ingestor_config.yaml:10-12`: the `cap` source file is
  `codice_rca.json`; `data/cleaned/cap/` has 96 files and none titled "Definizioni";
  `data/parsed/cap/codice_assicurazioni_private.json` has CAP art. 1 "Definizioni"
  (2 commas, 34,564 chars) and art. 274-bis (886).
- **FR-1 (sizes)** — CdS art. 2: 11 commas, 7,740 chars; art. 151: 1 comma, 3,565;
  art. 157 comma 1: ~900 chars, defines *arresto*, *fermata*, *sosta*, *sosta di
  emergenza* (verified by reading the text). `data/parsed/cds/codice_della_strada.json`
  contains 309 `ABROGAT`/`((` markers.
- **AD-1 / Package Structure** — `src/labeling/` layout (`agents/`, `configs/`,
  `exceptions/`, `mappers/`, `models/`, `repositories/`, `services/`, `wiring.py`),
  `labeling/services/golden_set_labeling_service.py` (a batch use case sequencing
  services), `retrieval_evaluation/label_main.py` (a standalone entry point: argparse,
  config load, `RunArtifactWriter.build_run_dir`, `build_llm_call_tracker`);
  `pyproject.toml:31-41` (scripts registered per package).
- **AD-5** — `labeling/configs/labeling_config.py` (`agents_dir` with `AliasChoices
  ("AGENTS_DIR", ...)`, `frozen`); `guidami_ai_patente/configs/app_config.py`
  (`BaseConfig`, `postgres: PostgresConnectionConfig`, `yaml_file`); `commons/configs/`
  (`BaseConfig`, `PostgresConnectionConfig`, `OpenRouterConfig`).
- **FR-4** — `commons/ai/embedding/services/embedding_service.py`
  (`EmbeddingService(UseCase[Sequence[str], list[list[float]]])`);
  `commons/clients/postgres_client.py` exposes `execute`, `execute_many`,
  `execute_many_returning`, `fetch`, `truncate` and no explicit transaction API, hence
  the upsert-then-delete ordering instead of a transaction requirement.
- **AD-4** — `db/init.sql:74-86` (`quiz_question_embeddings.embedding_3_small VECTOR(1536)`
  with the `num_nonnulls` CHECK), `:20,24,38,43` (generated `tsvector` columns with GIN
  indexes).
- **AD-2** — `labeling/agents/comma_labeler/` and spec 0014: the `output_validator`
  precedent.
- **AD-8** — `ingestor/services/knowledge/article_cleaner.py:6-9`: the inline-markup
  pattern and its `ParsedArticleModel` signature.
- **FR-4 / AD-9** — `agents/explanation_translator/explanation_translator_agent.py:14-38`
  and `configs/agents/explanation_translator.yaml`: the `.ru`-suffixed agent shape and
  domain-register prompt this term translator's (much narrower) prompt follows;
  `docs/superpowers/specs/2026-09-18-explanation-translator-design.md` FR-8/AD-9 (the
  2026-09-22 amendment): the translate endpoint's `hints` field is exactly what
  `term_ru` is produced to feed.
- **AD-1a** — verified by inspecting the installed package
  (`.venv/Lib/site-packages/pywire/`): `decorators.py`, `container.py` and `__init__.py`
  contain no reference to `fastapi`, confirming the core container (decorators,
  `Autowired[T]`, `register_instance`, `resolve`, `close`) is usable standalone; only
  the separate `fastapi.py` module depends on it, and this package never imports that
  module. `.claude/rules/pywire-di.md` (updated in this round) records the exception
  by name.

## Open Questions

- [ ] **blocking for the plan** — Feasibility of extracting CAP art. 1 (~34k chars) with a
  verbatim guarantee: the model must reproduce ~34k characters of output. Proposed:
  chunk at entry boundaries (`max_block_chars`) and validate per chunk; confirm with a
  spike on art. 157 then art. 3 before committing to the chunk size.
- [ ] **for the requester** — Review of the extracted Italian definitions. With no file
  layer (AD-6), a bad extraction is corrected by SQL `UPDATE` and lost on `--force`. If
  that is not acceptable, the cheapest addition is a per-block JSON file written between
  extraction and embedding and read back on rerun — a second read/write repository
  pair, but still inside this package and still no `ingest` command. Confirm that
  DB-only is enough.
- [ ] **non-blocking** — Package name: `glossary` (proposed) versus a more specific
  `definition_glossary`; `src/glossary/` sits beside `labeling` and `retrieval_evaluation`.
- [ ] **non-blocking** — Whether CdS art. 2 is extracted at article level (all 11 commas)
  or only the comma holding the class definitions; comma 1's shape was not read in
  detail.
- [ ] **non-blocking** — Exact prompt for the extractor, chunk size and `max_tokens` —
  left to implementation.

## Follow-ups after implementation

- Run `second-brain:update` (`database.md`, `architecture.md`, `patterns.md`, `layout.md`,
  `testing.md`) and record an ADR (`second-brain:adr`) for: a derived glossary table
  instead of splitting corpus commas, a standalone package instead of an ingestor
  entity, and LLM extraction with a verbatim validator.
- Update the `CLAUDE.md` scripts table with `build-glossary`.

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by the assistant on 2026-09-21/22, based on the Feasibility
  Evidence above (source and data reads, not a dedicated feasibility-compiling skill)

## Changelog

- **2026-09-22 (latest)** — Switched the package's own DI from manual constructor
  injection to pywire (AD-1a), at the requester's explicit direction ("non vedo perché
  no" against the batch-package default in `pywire-di.md`). Verified the container has
  no FastAPI dependency of its own, so it works in a plain script; updated
  `.claude/rules/pywire-di.md` to record this as a named, narrow exception —
  `labeling`/`retrieval_evaluation`/the ingestor stay on manual DI, unchanged, per the
  requester's own choice to scope this to `glossary` only, not a blanket migration.
- **2026-09-22 (later)** — Reinstated a *minimal* translation step after the requester
  asked whether the translate endpoint could accept translation hints: one new agent
  (`GlossaryTermTranslatorAgent`) and one new column (`term_ru`) — the term only, never
  the definition. `term_ru` is consumed exclusively as a hint by spec 0018's FR-8/AD-9
  amendment (added in the same round); this spec still builds no consumer of its own.
- **2026-09-22** — Dropped translation entirely, after the backend/bot redesign
  (spec 0020) made per-entry Russian dead weight: `GlossaryTranslatorAgent`, the three
  `*_ru` columns and `translation_batch_size` are removed; `definition_it` renamed to
  `definition` (only one language exists now). Added the "Independence from Spec 0020"
  section, making the two specs implementable in either order and naming this spec as
  the DDL's source of truth.
- **2026-09-21** — Reshaped: the requester asked for a standalone package with its own
  agents, data model, read/write repositories and services, so the ingestor stays clean
  and no `ingest` command is added. Removed the `prepare`/`index`/`reset` entities, the
  enriched-file layer and the `ingest status`/`reset` integration; added the package
  structure, its own config root and the failure semantics (a failing block does not stop
  its siblings).
- **2026-09-21** — Initial draft. Split out of the first draft of spec 0020 after the
  requester chose a precomputed glossary table (embedding, full-text, Italian definition,
  Russian translation) over passing whole definition articles in each prompt; extraction
  method chosen in grilling (LLM agent with a verbatim validator). Found during this
  work: CAP art. 1 is outside the indexed corpus, so the glossary reads the parsed layer.
