# ADR 0012: The `enriched` Data Layer Is Version-Controlled

## Status

Accepted — supersedes ADR 0005.

## Context

ADR 0005 kept `data/enriched/` out of version control, treating it as a
regenerable build artifact: LLM output is non-deterministic, reproducible
from `cleaned` plus config, and expensive to regenerate, so it was handled
as a local cache rather than a pinned asset.

The exclusion was reversed in practice on 2026-08-05: commit `5e60b63`
removed both `data/enriched/` and `data/test-data/enriched/` from
`.gitignore`, and `6bf8d23` committed the 7099 `EnrichedQuizModel` files
under `data/enriched/quiz-patente-ab/`. Neither commit recorded a
rationale, and ADR 0005 was left stating the opposite of what the
repository does — the drift this ADR closes.

Two things changed since ADR 0005 was written, and both invert its
reasoning rather than merely outweighing it.

**The layer became the fixed input to a measurement.** Spec 0007 builds a
retrieval evaluation harness and spec 0008 uses it to compare six query
representations against each other. Every one of those measurements is
computed downstream of `enriched`. ADR 0005 treated non-determinism as a
reason not to track the layer; once the layer feeds a comparison, it is
precisely the reason it must be pinned. If the input can change underneath
the experiment, two runs are not comparable, and a movement in the numbers
cannot be attributed to the change under test.

**The cost argument pointed the wrong way.** ADR 0005 listed
"cost-bearing to regenerate" as grounds for treating the layer as a local
cache. Expense is an argument for durability, not against it: an asset that
is costly to rebuild and exists in exactly one untracked local directory is
one wiped volume or one fresh clone away from having to be bought again.

That risk was not hypothetical. On 2026-08-06 the Postgres volume was
recreated, `db/init.sql` ran, and every row was lost — 770 articles, 3992
commas, 7099 quiz questions. The corpus side was recoverable for a few cents
because `cleaned` is tracked. The quiz side was recoverable **only because
`enriched` had been committed the day before**; under ADR 0005 it would have
required a full re-enrichment — one vision call per distinct image (427,
per ADR 0003) plus the deduplicated norm-reference calls across the bank.

## Decision

Track `data/enriched/` in git, on the same terms as `data/raw/`,
`data/parsed/`, and `data/cleaned/`. `data/test-data/enriched/` is tracked
on the same terms once it exists; it is currently absent, not ignored.

The tracked/untracked boundary no longer coincides with the
deterministic/non-deterministic boundary. The line is now drawn at
**reproducibility cost**: an artifact that is expensive or non-deterministic
to rebuild is pinned, precisely so that what downstream work is measured
against is fixed and auditable. Cheap deterministic derivatives (the
database contents, `logs/`) stay out.

Regenerating the layer stays an explicit, deliberate act
(`ingest prepare quiz --force`), and its diff is reviewed like any other
change to a committed asset.

## Alternatives considered

- **Keep ADR 0005 as written**: rejected — it describes a repository that
  no longer exists, and the volume loss of 2026-08-06 demonstrated the
  concrete failure mode it accepted.
- **Track it but squash the history (shallow snapshot, force-updated)**:
  rejected — the point of pinning is that the input to an experiment is
  auditable over time; discarding history keeps the storage saving but
  removes the reason to track it at all.
- **Move it out of git into external object storage**: rejected — adds an
  out-of-band dependency and a credential to a repository that today needs
  neither, to avoid 7099 small JSON files.

## Consequences

- A fresh clone can run `ingest index quiz` immediately, with no LLM spend.
  This is what makes spec 0008's FR-4 ("re-ingestion without
  re-enrichment") satisfiable at all.
- ADR 0005's noisy-diff concern is now an accepted cost, not a refuted one:
  a deliberate re-enrichment produces a large, mostly-wording diff. This is
  tolerable because re-enrichment is rare and explicit; it would stop being
  tolerable if enrichment were re-run routinely.
- The repository carries 7099 small JSON files, and grows by roughly that
  much again for every future enriched corpus.
- Reviewing enrichment quality is now possible through a PR diff, which
  ADR 0005 explicitly listed as unavailable.
- The deterministic/non-deterministic boundary no longer tells you what is
  tracked. Anyone adding a pipeline layer must decide its version-control
  status on reproducibility cost, and state it — the rule is no longer
  derivable from where the LLM calls happen.

*Supersedes ADR 0005. Realized by commits `5e60b63` (`.gitignore`) and
`6bf8d23` (the data itself), which predate this ADR.*
