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
| **Status** | implemented |
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
| CdS art. 2 comma 1 (definition of "strada") | `cds/codice_della_strada.json` | 1 | 0.2k chars |
| CdS art. 2 comma 3 (road category definitions) | `cds/codice_della_strada.json` | 3 | 2.7k |
| CdS art. 2 comma 4 (definition of "strada di servizio") | `cds/codice_della_strada.json` | 4 | 0.4k |
| CdS art. 3 (road and traffic definitions) | `cds/codice_della_strada.json` | 1 | 11.3k |
| CdS art. 151 (light-signal definitions) | `cds/codice_della_strada.json` | 1 | 3.6k |
| CdS art. 157 (arresto, fermata, sosta) | `cds/codice_della_strada.json` | 1 | 0.9k |
| CAP art. 1 (insurance definitions) | `cap/codice_assicurazioni_private.json` | 1 | ~34k |

CdS art. 2 is three narrow blocks, not one block over all 11 commas: comma 2 is a bare
code→label list with no explanatory text ("A - Autostrade; B - Strade extraurbane
principali; …") and commas 5–10-bis are the administrative classification/
declassification procedure (Ministero delle infrastrutture role, decree references) —
neither holds a term definition, and feeding them to the extractor would only risk a
spurious entry the verbatim validator cannot catch (it checks the text exists, not that
it is a definition). Confirmed by reading the parsed text (2026-09-24 grilling round).

Files are read from `GlossaryConfig.parsed_dir` (default `data/parsed`), **never** from
the database and never from the RCA-filtered `codice_rca.json`. The block text is the
concatenation of the selected commas with the parser's inline `((…))` markup removed
(the same rule as the ingestor's cleaner, reimplemented in this package — see AD-8).

### FR-2: `uv run build-glossary [--force] [--dry-run]`

One new script, `build-glossary = "glossary.main:main"` under `[project.scripts]`. For
each configured block, in order: read its text (FR-1), skip it if the table already
holds entries for it and `--force` was not passed, otherwise extract (FR-3), embed and
write (FR-6). **This script never translates**: every row it writes has `term_ru = NULL`
— translation is a fully separate script (FR-5), so a translation failure can never
fail, retry, or block an extraction that has nothing to do with it (AD-11).

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
entries when it exceeds `GlossaryConfig.max_block_chars`, at a boundary found
mechanically, not by the model — see AD-10) and returns `list[{term, definition}]`,
skipping repealed entries. Its `output_validator` raises `ModelRetry` (message in
Italian) when:

- a `definition` is not, after whitespace normalization, a substring of the block text;
- a `term` is empty or does not occur in the block text;
- two entries share the same `term`.

The model can therefore select and split, never rewrite, the normative text.

A block's chunks are extracted independently but accumulated in memory before anything
is written: FR-6's embed-and-write step only runs once every chunk of a block has
succeeded. A chunk failure (including an exhausted validator retry) therefore fails the
*whole* block — nothing partial is written — so a later non-`--force` run still finds
the block empty and retries it in full, rather than treating a half-extracted block as
already built (FR-7).

### FR-4: The term (not the definition) is translated once, as a future hint

`GlossaryTermTranslatorAgent` (`configs/agents/glossary_term_translator.ru.yaml`,
language-suffixed per `.claude/rules/agent-config-naming.md`: unlike the extractor, its
whole job is producing a Russian rendering) receives entries in batches
(`GlossaryConfig.translation_batch_size`) and returns, per entry, `term_ru`: the
official Russian road-traffic term (`max_length=80`). Nothing else is translated — no
definition, no summary. A batch response that does not return exactly one item per
input entry, in order, is rejected (`ModelRetry`).

This agent is invoked exclusively by `translate-glossary-terms` (FR-5), never by
`build-glossary` (FR-2) — see AD-11 for why the two are separate scripts.

`term_ru` is stored for exactly one purpose: to be handed to
`POST /explanations/translate` as a translation hint (spec 0018, FR-8/AD-9, amended for
this spec) when spec 0020 assembles its final, translatable explanation text. It is
never returned by any API response field of its own, and this spec builds no
consumer for it — that is spec 0020's job.

### FR-5: `uv run translate-glossary-terms [--force] [--dry-run]`

A second, independent script, `translate-glossary-terms = "glossary.translate_main:main"`
under `[project.scripts]`, in the same `src/glossary/` package. It never touches
extraction, embedding, `definition`, or any block config — it only fills `term_ru`.

`GlossaryTermTranslationRunService` (an `AsyncUseCase[GlossaryTermTranslationRequest,
GlossaryTermTranslationReport]`) sequences: read every row with `term_ru IS NULL`
(`GlossaryTermReadRepository`) — or, with `--force`, every row regardless of its current
`term_ru` —, translate them in batches of `GlossaryConfig.translation_batch_size`
through `GlossaryTermTranslatorAgent` (FR-4), and write each successful batch's
`term_ru` back by id (`GlossaryTermUpdateRepository`, a plain `UPDATE`, no upsert, no
reconciliation).

- A failing batch (including an exhausted validator retry) is logged at `error` with
  the term ids it covered and skipped; the remaining batches still run. After the last
  batch, if any batch failed, the run raises `GlossaryTranslationError` listing them and
  exits non-zero — rows from failed batches simply keep `term_ru = NULL` and are picked
  up automatically by the next run's default (non-`--force`) selection.
- `--dry-run` prints the step chain that would run and exits: no filesystem write, no
  LLM call, no database connection — symmetric with FR-2.
- Every real run logs to the console and to
  `logs/translate_glossary_terms_<timestamp>/run.log` (`RunArtifactWriter`, as FR-2).
- It ends with a summary (rows translated, rows still `term_ru = NULL`) printed to
  stdout.

### FR-6: Embed and write, idempotently

Each entry is embedded as `f"{term}\n{definition}"` through the existing `commons`
`EmbeddingService` (`text-embedding-3-small`, stored in `embedding_3_small`), then
written by `GlossaryEntryWriteRepository`: **upsert** by the natural key first (with
`term_ru = NULL` — FR-4/FR-5 fills it in independently, later), then **delete** the
block's entries that no longer appear, scoped to that block (the reconciliation pattern
of spec 0010). The order matters: a failure between the two statements leaves at worst a
few stale extra rows, never an empty block, and a rerun converges.

### FR-7: A failing block fails the run, not its siblings

A block whose extraction, embedding or write fails (including an exhausted validator
retry) is logged at `error` with its id and skipped; the remaining blocks still run.
After the last block, if any block failed, the run raises `GlossaryBuildError` listing
them and exits non-zero. Blocks already written stay written. This is `build-glossary`'s
own failure isolation; `translate-glossary-terms` has its own, symmetric, at the batch
level (FR-5).

### FR-8: The table

`glossary_entries` (Data Model): Italian term and definition, the term's Russian
rendering (FR-4, nullable — filled independently by FR-5), provenance columns
(`source`, `article_number`, `comma_number`), an `embedding_3_small` column and a
generated full-text column on the term. No foreign key to `articles` or to any quiz
table (AD-3).

### FR-9: Both scripts are cheap and bounded

`build-glossary`: one extraction call per block chunk — on the order of a dozen calls
for the initial set of blocks. `translate-glossary-terms`: one translation call per
`translation_batch_size` terms — on the order of a few dozen calls for ~250 terms.
Together, still a few dozen calls total; each script runs its own work sequentially,
there is no concurrency knob (YAGNI at this size).

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
├── translate_main.py             # entry point: `translate-glossary-terms`; its own
│                                  #   composition root
├── wiring.py                     # builds the few commons primitives pywire can't:
│                                  #   PostgresClient, EmbeddingService, OpenRouter provider
│                                  #   (shared by both entry points)
├── configs/
│   └── glossary_config.py        # GlossaryConfig, GlossaryBlockConfig (frozen) — data, not
│                                  #   a component; registered via register_instance (AD-1a)
├── agents/
│   ├── glossary_extractor/           # GlossaryExtractorAgent (@agent) + dto/
│   └── glossary_term_translator/     # GlossaryTermTranslatorAgent (@agent) + dto/
├── models/                       # GlossaryBlock, ExtractedEntry, TranslatedTerm, BlockOutcome,
│                                  #   GlossaryBuildRequest/Report,
│                                  #   GlossaryTermTranslationRequest/Report
├── mappers/                      # GlossaryEntryMapper: extracted + vector → entity (term_ru=NULL)
├── repositories/
│   ├── glossary_block_read_repository.py    # (@repository) parsed article file → block text
│   ├── glossary_entry_read_repository.py    # (@repository) DB: does this block already have entries?
│   ├── glossary_entry_write_repository.py   # (@repository) DB: upsert + scoped reconciliation
│   ├── glossary_term_read_repository.py     # (@repository) DB: rows with term_ru IS NULL (or all, --force)
│   └── glossary_term_update_repository.py   # (@repository) DB: UPDATE term_ru by id
├── services/
│   ├── glossary_extraction_service.py            # (@service) block text → extracted entries
│   ├── glossary_term_translation_service.py      # (@service) entry batch → term_ru (no DB access)
│   ├── glossary_build_service.py                 # (@service) sequences build-glossary, block by block
│   └── glossary_term_translation_run_service.py  # (@service) sequences translate-glossary-terms
└── exceptions/                   # GlossaryBuildError, GlossaryTranslationError
```

Every class above except `configs/` declares its collaborators as `Autowired[T]` class
fields — no constructor-parameter DI for them, per `pywire-di.md`'s "Convention" section,
applied here exactly as it is in `guidami_ai_patente`.

| Piece | Role |
|---|---|
| `GlossaryBuildService` | An `AsyncUseCase[GlossaryBuildRequest, GlossaryBuildReport]` `@service` (request: `force`; report: one `BlockOutcome` per block), like `GoldenSetLabelingService` — sequencing lives in a service here, as in `labeling`, rather than in an `orchestrators/` package. Invoked via `__call__` (`use-case-invocation.md`). Owns `build-glossary`'s pipeline only — it never calls the term translator (AD-11). |
| `GlossaryExtractionService` | One responsibility: run the extractor agent over one block's text with chunking and return typed entries. `@service`, `AsyncUseCase`. |
| `GlossaryTermTranslationService` | One responsibility: run the term translator agent over one batch of entries and return each entry's `term_ru`. `@service`, `AsyncUseCase`. Does not read or write the database itself. |
| `GlossaryTermTranslationRunService` | An `AsyncUseCase[GlossaryTermTranslationRequest, GlossaryTermTranslationReport]` `@service` (request: `force`; report: rows translated/skipped, failed batch ids) — sequences `translate-glossary-terms`: read rows missing `term_ru`, call `GlossaryTermTranslationService` per batch, write each batch back, isolate failures per batch (FR-5). Mirrors `GlossaryBuildService`'s role for the other script. Invoked via `__call__`. |
| Read repositories | `@repository`, one per distinct query shape: block source (files, used by `build-glossary`), "already built?" (DB, per block, used by `build-glossary`), "needs translation?" (DB, per row, used by `translate-glossary-terms`). Each is used by exactly one script. |
| Write repositories | `@repository`. `GlossaryEntryWriteRepository` is the only class that writes `glossary_entries`' extraction columns (upsert + reconciliation, always `term_ru = NULL`); `GlossaryTermUpdateRepository` is the only class that ever writes `term_ru` (plain `UPDATE` by id). Neither touches the other's columns. |
| `main.py` / `translate_main.py` | Each loads `GlossaryConfig`, `OpenRouterConfig` and `ObservabilityConfig` **once, here** (`rules/python/architecture.md`); both build the handful of `commons` primitives pywire cannot construct itself (`wiring.py`, shared) and register them with `register_instance`; then each resolves and runs its own top-level service (`GlossaryBuildService` / `GlossaryTermTranslationRunService`). No `pywire.fastapi`, no lifespan — `container.close()` at the end of each fires any `@pre_destroy` hook (e.g. closing the Postgres pool). |

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

### AD-10: Chunk boundaries are found mechanically, not guessed by the model

The two blocks needing chunking under a realistic `max_block_chars` both carry a
regular top-level enumeration marker: CdS art. 3 is `N) TERM: definizione.` (numeric),
CAP art. 1 is `lettera) termine: definizione;` (a…z, aa…qqq — verified: 48+ top-level
markers over 34,344 characters). `max_block_chars` chunking therefore splits at the
block's own marker (a small per-block regex, mirroring AD-8's "reimplement the little
that's needed" stance), packing consecutive entries up to the limit; a block with no
detectable marker (there is none among the initial set) falls back to a raw
character-count split. This is boundary-detection only — it never extracts a term or
definition itself, so it does not reintroduce the four fragile per-format parsers
rejected in Problem & Motivation; the model still does all term/definition extraction
and is still verbatim-validated per chunk (AD-2).

Chosen (2026-09-24 grilling round) over leaving chunking to raw `max_block_chars` cuts
validated only by a live spike before the plan could be written: with mechanical
boundaries, the model is never asked to locate a cut inside a wall of text, which was
the actual source of the original feasibility risk for CAP art. 1's ~34k characters.
The spike itself (art. 157 → art. 3 → CAP art. 1, see Testing) is still valuable and
still runs, but as an implementation-time validation of extraction *quality*, not as a
plan-blocking feasibility gate.

### AD-11: Translation runs as a second, fully decoupled script

Chosen (2026-09-24 grilling round) over running translation inside `build-glossary`'s
own per-block pipeline: `build-glossary` must never fail, retry, or skip a block because
a *word* failed to translate — extraction, embedding and the Italian `definition` are
the thing spec 0020 actually depends on; `term_ru` is only ever consumed as an optional
hint (FR-4). AD-9 already separated translation into a different *agent* for exactly
this reason ("a translation failure should not discard an otherwise-valid extraction");
this decision extends that separation from the agent boundary to the process boundary —
two scripts, two entry points, two `AsyncUseCase`s, meeting only at the same table's
different columns (`GlossaryEntryWriteRepository` never writes `term_ru`;
`GlossaryTermUpdateRepository` never writes anything else).

Consequences:

- `term_ru` becomes nullable (Data Model) — a row is a complete, usable glossary entry
  with `term_ru = NULL`; spec 0020's consumer already treats a missing hint as absent,
  not as an error (spec 0018, FR-8/AD-9 amendment).
- `glossary_entries` is already live (Changelog, 2026-09-24: table, `GlossaryReadRepository`
  and the RRF retrieval depths shipped with spec 0020), so this is not a
  fresh-`init.sql`-only change: the implementation plan must add a `db/migrations/`
  script that drops the `NOT NULL` constraint on the real dev stack (`CLAUDE.md` path 2),
  alongside editing `db/init.sql` for a future fresh environment.
- `translate-glossary-terms` is retryable and idempotent on its own terms: it always
  selects exactly the rows that still need it (`term_ru IS NULL`, unless `--force`), so
  a partially-failed run needs no special recovery — just rerun it.

## Data Model

Table in `db/init.sql`. **Authoritative here** regardless of which plan (this spec's or
spec 0020's) lands it first — see Independence from Spec 0020. Already live on the dev
stack: spec 0020's plan landed first and applied it via
`db/migrations/0019_glossary_entries.sql` (Changelog, 2026-09-24) — so the `term_ru`
nullability change below (AD-11) needs its own new migration, not a fresh-environment
recreate (`CLAUDE.md` path 2).

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
    -- Nullable: build-glossary (FR-2/FR-6) always writes NULL here; only
    -- translate-glossary-terms (FR-5) ever writes a non-NULL value, via a separate
    -- UPDATE, not through this insert path (AD-11).
    term_ru           TEXT,
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
  `CARREGGIATA`); the written row's `term_ru` is `NULL`.
- **Term read repository** (unit, fixture rows): selects only rows with `term_ru IS
  NULL`; with `--force`, selects every row regardless of its current `term_ru`.
- **Term update repository** (`@pytest.mark.integration`): updates `term_ru` for the
  given id only; every other column (`term`, `definition`, `embedding_3_small`, …) is
  unchanged.
- **Translation run service** (unit, fakes): a failing batch is logged and skipped, the
  remaining batches still run, and the run raises `GlossaryTranslationError` listing the
  failed ones; a rerun with no `--force` only ever selects rows still `term_ru IS NULL`.
- **Entry points**: `build-glossary --dry-run` and `translate-glossary-terms --dry-run`
  each write nothing, open no connection and make no LLM call.
- A real-LLM `@pytest.mark.integration` spike over one small block (CdS art. 157) to
  validate extraction quality before the full run.

## Feasibility Evidence

Verified 2026-09-21/22 on branch `feat/backend`, plus a 2026-09-24 grilling round
(marked below).

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
- **FR-1 (CdS art. 2 comma scope, 2026-09-24)** — read all 11 commas of
  `data/parsed/cds/codice_della_strada.json`, article `2`: comma 1 (171 chars) defines
  "strada"; comma 2 (354 chars) is a bare code→label list ("A - Autostrade; B - Strade
  extraurbane principali; …") with no explanatory text; comma 3 (2,702 chars) is the
  actual category definitions ("A - AUTOSTRADA: strada extraurbana o urbana a
  carreggiate indipendenti…"); comma 4 (380 chars) defines "strada di servizio"; commas
  5–10-bis (5 commas, ~3.9k chars total) are the administrative classification
  procedure, with no term definitions.
- **AD-10 (chunk markers, 2026-09-24)** — regex scan of
  `data/parsed/cap/codice_assicurazioni_private.json` article `1` comma 1 (34,344
  chars): 48 top-level `lettera) ` markers (`a`…`z`, `aa`…`qqq`), none in comma 2 (220
  chars, out of scope for chunking — the whole comma is under any reasonable
  `max_block_chars`). `data/parsed/cds/codice_della_strada.json` article `3` comma 1
  opens `1) AREA DI INTERSEZIONE: … 2) Area pedonale: …` — the same regular numeric
  `N) ` marker pattern, distinct format from CAP's but equally mechanical.
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
- **FR-6** — `commons/ai/embedding/services/embedding_service.py`
  (`EmbeddingService(UseCase[Sequence[str], list[list[float]]])`);
  `commons/clients/postgres_client.py` exposes `execute`, `execute_many`,
  `execute_many_returning`, `fetch`, `truncate` and no explicit transaction API, hence
  the upsert-then-delete ordering instead of a transaction requirement.
- **AD-11 (table already live, 2026-09-24)** — `docs/second-brain/database.md:230,339,
  345,597-598` confirm `glossary_entries` was created via spec 0020's
  `db/migrations/0019_glossary_entries.sql` (spec 0020's plan landed first); `db/init.sql:
  234-253` currently declares `term_ru TEXT NOT NULL` — both need a follow-up migration
  and an `init.sql` edit for this decision (Data Model, Follow-ups).
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

Four of the five items from the initial draft (both blocking items, the package name,
and CdS art. 2's comma scope) were resolved in the 2026-09-24 grilling round (see
Changelog); each resolution is folded into FR-1, FR-3, AD-10 and the Feasibility
Evidence above rather than kept as a standing checklist item. One remains:

- [ ] **non-blocking** — Exact prompt for the extractor and the term translator, and
  chunk/batch size and `max_tokens` for both — left to implementation.

## Follow-ups after implementation

- Run `second-brain:update` (`database.md`, `architecture.md`, `patterns.md`, `layout.md`,
  `testing.md`) and record an ADR (`second-brain:adr`) for: a derived glossary table
  instead of splitting corpus commas, a standalone package instead of an ingestor
  entity, LLM extraction with a verbatim validator, and translation as a fully separate,
  independently-retryable script (AD-11).
- Update the `CLAUDE.md` scripts table with `build-glossary` and
  `translate-glossary-terms`.
- Write and apply the `db/migrations/` script that drops `term_ru`'s `NOT NULL`
  constraint on the live dev stack (AD-11) — `glossary_entries` already exists there via
  spec 0020's `db/migrations/0019_glossary_entries.sql` — and edit `db/init.sql` to match
  for a future fresh environment.

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by the assistant on 2026-09-21/22, based on the Feasibility
  Evidence above (source and data reads, not a dedicated feasibility-compiling skill)

## Changelog

- **2026-09-24 (later, latest)** — Third grilling round, triggered by a citation bug
  spotted in FR-2 ("embed and write (FR-4)" — FR-4 is actually the translation
  requirement, embed-and-write is what's now FR-6) and what that bug was hiding:
  `build-glossary` had no defined behavior for a translation failure despite `term_ru`
  being `NOT NULL`. At the requester's explicit direction ("non voglio che fallisca
  un'estrazione per non aver tradotto una parola — meglio fare in due step"), resolved
  by fully decoupling translation into its own script (AD-11): new FR-5
  (`translate-glossary-terms`), renumbered FR-5→6, FR-6→7, FR-7→8, FR-8→9; `term_ru`
  made nullable; two new repositories (`GlossaryTermReadRepository`,
  `GlossaryTermUpdateRepository`) and a new orchestrating service
  (`GlossaryTermTranslationRunService`, mirroring `GlossaryBuildService`), with the same
  failure-isolation shape as FR-7 but at the batch level (`GlossaryTranslationError`).
  Also fixed the Feasibility Evidence bullet that inherited the same FR-4/FR-6 mislabel.
  Confirmed acceptable as-is, no spec change needed: cross-block duplicate terms (the
  natural key is per-block, not global — spec 0020's retrieval already ranks multiple
  candidates) and per-block chunk atomicity (a block's chunks accumulate in memory;
  nothing is written until every chunk succeeds — now stated explicitly in FR-3). Noted
  a real consequence surfaced mid-round: `glossary_entries` is already live on the dev
  stack (spec 0020's plan landed it first), so `term_ru`'s nullability change needs a
  new `db/migrations/` script, not just an `init.sql` edit (Follow-ups). Widened the one
  remaining Open Question to also cover the term translator's prompt/batch tuning, now
  that it is a peer script rather than a step folded into `build-glossary`.
- **2026-09-24** — Grilling round, run after spec 0020 (this glossary's sole
  planned consumer) shipped and was signed off: `glossary_entries`, `GlossaryReadRepository`
  and the RRF retrieval depths (`dense_k`/`text_k`/`max_candidates` = 5/5/10) are live
  and hold up against this spec's assumptions unchanged (cross-checked `term_ru`'s only
  actual consumer, `QuizExplanationResponse.translation_hints`, against FR-4 — no
  conflict). Resolved all five Open Questions: (1) AD-10 added — chunking finds its
  boundary mechanically at each block's own regular enumeration marker (verified on
  CAP art. 1 and CdS art. 3), so the CAP art. 1 verbatim-extraction risk is no longer a
  plan-blocking gate, only an implementation-time quality spike; (2) AD-6 (DB-only, no
  review file layer) confirmed as-is; (3) CdS art. 2 split into three narrow blocks
  (commas 1, 3, 4 — the only ones holding a term definition, verified by reading all 11
  commas), dropping the "all commas" block; (4) package name `glossary` confirmed; (5)
  the extractor's exact prompt/chunk size stays left to implementation, the one item
  still genuinely open.
- **2026-09-22** — Switched the package's own DI from manual constructor
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
