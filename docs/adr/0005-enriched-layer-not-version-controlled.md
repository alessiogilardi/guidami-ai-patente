# ADR 0005: The `enriched` Data Layer Is Not Version-Controlled

## Status

Accepted

## Context

`data/raw/`, `data/parsed/`, and `data/cleaned/` are all tracked in git.
`data/enriched/` — the quiz pipeline's post-LLM-enrichment layer (see
**layer** in `glossary.md`) — is listed in `.gitignore` instead, with no
prior written rationale; the exclusion existed in `.gitignore` but was
undocumented until this ADR.

The `enriched` layer holds `EnrichedQuizModel` output: `image_description`
/ `image_analysis` from `ImageDescriptionEnricher`
(`RoadSignDescriberAgent`, one vision call per distinct image — ADR 0003)
and norm references from `NormReferenceEnricher`
(`NormReferenceDescriberAgent`). Both enrichers make LLM calls. Unlike
`raw` → `parsed` → `cleaned`, which are deterministic transforms of fixed
source material (scraped HTML/PDF text), `enriched` is model-generated:
re-running enrichment on unchanged `cleaned` input can yield different
wording, and a model/prompt change changes the output outright.

## Decision

Keep `data/enriched/` out of version control (`.gitignore:525`). Treat it
as a regenerable build artifact of the `cleaned` → `enriched` step, not a
pinned source-of-truth asset:

- **Non-deterministic**: LLM output isn't guaranteed stable across runs,
  so committing a snapshot would drift from what a fresh run produces and
  create noisy diffs unrelated to any real data or code change.
- **Reproducible from `cleaned` + config**: given the same `cleaned` input
  and the same enrichment config/prompts, the layer can always be
  regenerated (`ingest prepare quiz`); it carries no information that
  can't be reconstructed downstream of tracked inputs.
- **Cost-bearing to regenerate**: each run issues real vision/LLM calls
  (billed, logged in `llm_call_logs`), so the layer is treated as a local
  cache of an expensive computation, not something to keep syncing across
  commits.

## Alternatives considered

- **Track it like `raw`/`parsed`/`cleaned`**: rejected — every re-run
  would produce a diff-only-in-wording commit even when nothing
  meaningful changed, and the repo would carry the cost of storing
  regenerable, non-deterministic content indefinitely.
- **Track it but only update on deliberate re-enrichment (manual
  commit discipline)**: rejected — relies on remembering to commit after
  every `ingest prepare quiz`, with no mechanical enforcement; the
  cleaned/enriched boundary is exactly where determinism ends, so it's a
  natural place to draw the tracked/untracked line instead.

## Consequences

- A fresh clone has no `data/enriched/` and must run
  `uv run ingest prepare quiz` (LLM calls, billed) before `ingest index
  quiz` can embed and store the quiz bank — there is no way to get
  enriched data except by regenerating it.
- Enrichment output isn't diffable/reviewable via git; any review of
  `image_description`/norm-reference quality has to happen through the
  HTML review viewer or ad hoc inspection of the local `data/enriched/`
  files, not through a PR diff.
- The tracked/untracked boundary now doubles as the deterministic/
  non-deterministic boundary in the pipeline — worth keeping in mind if a
  future layer is added between `cleaned` and `enriched`, or if `cleaned`
  itself ever gains a non-deterministic step.

*Referenced from `.gitignore:525` (comment added alongside this ADR).*
