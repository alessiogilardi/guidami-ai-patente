# ADR 0036: The glossary is a new, independently-owned derived table, not a split of `article_commas`

## Status

Proposed

## Context

Spec 0020's explanation endpoint needs per-term definitions (e.g. "carreggiata",
"banchina") to ground unfamiliar vocabulary. The definitions already exist in the
corpus, but not in a usable shape: CdS art. 3 comma 1 is one ~11,300-character string
holding ~65 definitions, stored as a single `article_commas` row with a single vector —
no per-term retrieval is possible over it, and the same problem repeats for CdS art. 2,
151, 157 and the CAP definitions article, each in a different textual format. Worse, CAP
art. 1 ("Definizioni") is not in the indexed corpus at all: the `cap` source is
`codice_rca.json`, filtered down to RCA-relevant articles by `rca_ranges`, so the
largest definitions article is silently absent from anything reading `article_commas`.

The corpus schema (`articles`/`article_commas`) is shared, load-bearing state: it is the
candidate set every comma-labeling run and every golden-set verdict was computed
against, under the labeling configuration epoch (`docs/second-brain/database.md`,
`LabelingEpoch`). Any change to what a "comma" is or how many exist per article changes
that candidate set's meaning retroactively.

## Decision

Definitions are extracted into a new, standalone table, `glossary_entries` — one row per
term, holding its Italian definition, an embedding and a full-text index — built and
owned entirely by a new standalone package, `src/glossary/` (see ADR 0037). Provenance
back to the source law is recorded as plain text columns (`source`, `article_number`,
`comma_number`), never a foreign key into `articles`/`article_commas`. The pipeline
reads already-parsed JSON files directly and writes straight to `glossary_entries`, with
no intermediate committed artifact (idempotency comes from the natural key
`(source, article_number, comma_number, term)` plus skip-unless-`--force`, not from a
review file). `glossary_entries` has exactly one writer (`build-glossary`); spec 0020's
`GlossaryReadRepository` (a different package, `guidami_ai_patente`) is a reader only —
the two packages never import each other and meet solely at the table.

## Alternatives considered

- **Split the definitions articles into one comma per term inside `articles`/
  `article_commas`**: rejected outright — it would change the shared corpus schema,
  altering the labeling candidate set and therefore the meaning of the configuration
  epoch and of every golden-set verdict already computed, for a feature (definition
  lookup) that has nothing to do with labeling.
- **Read the definition text live from the corpus database** at explanation time
  instead of precomputing a table: rejected — CAP art. 1 isn't in the indexed corpus at
  all, so this would silently and permanently lack the largest definitions article; it
  would also couple the glossary's availability to corpus-ingestion ordering.
- **A foreign key from `glossary_entries` back to `articles`/`article_commas`**:
  rejected in favor of plain text provenance columns — `ingest reset knowledge`
  truncates `articles`, and the glossary is deliberately independent of that lifecycle
  (built from parsed files, not from the corpus database); a FK would force the two
  lifecycles to move together for no functional benefit.
- **A committed per-block JSON file as a review/versioning layer** between extraction
  and the database write: deferred for simplicity — the pipeline writes straight to the
  table instead. Accepted consequence: a correction to a definition is an unversioned
  SQL `UPDATE`, and is silently overwritten the next time that block is rebuilt with
  `--force`.

## Consequences

A future schema change to `articles`/`article_commas` (e.g. a comma-splitting migration)
can proceed without touching the labeling epoch's candidate set, and without needing to
account for the glossary at all — the two are structurally decoupled. The cost: there is
no foreign-key integrity check tying a `glossary_entries` row back to a real corpus
comma, so a stale or renumbered article/comma reference in `glossary_entries` would go
undetected by the database itself (would only surface as a block that silently stops
matching anything on a rebuild). There is also no versioning or review step for a
definition correction — an operator must accept that a hand-edited row is either
preserved forever or silently overwritten on the next `--force` rebuild of its block,
whichever comes first; a future spec would need to introduce review/versioning if that
gap becomes a real problem.
