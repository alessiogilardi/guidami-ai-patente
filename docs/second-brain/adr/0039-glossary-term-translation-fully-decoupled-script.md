# ADR 0039: Term translation runs as a second, fully decoupled agent and script, never inside `build-glossary`'s own pipeline

## Status

Proposed

## Context

Spec 0018 already translates a whole explanation message on demand via
`ExplanationTranslatorAgent`, so a full Russian translation of each glossary
definition/summary was considered and rejected outright: nothing would ever read it —
the entry that consumes this glossary (`QuestionExplainerAgent`, spec 0020) writes
Italian, merges it into one explanation message, and that whole message is what gets
translated once, on demand. Only the *term itself* needs a pre-agreed Russian rendering
(a translation hint, spec 0020 FR-4), not its definition.

Given that narrower scope, the remaining question was where the term-translation step
should live. `build-glossary`'s own per-block pipeline (extract → embed → write) was the
obvious first place to put it — translate each term right after extracting it, in the
same run. This was rejected in a 2026-09-24 grilling round: `build-glossary` must never
fail, retry, or skip a block because a *translation* failed. Extraction, embedding and
the Italian `definition` are what spec 0020's grounding actually depends on;
`term_ru` is only ever consumed as an optional hint (FR-4) — a missing translation should
never be allowed to hold back an otherwise-valid, already-verbatim-validated extraction.

## Decision

Term translation to Russian is a second agent, `GlossaryTermTranslatorAgent`, entirely
separate from `GlossaryExtractorAgent`, and a second, independently-runnable script,
`translate-glossary-terms`, entirely separate from `build-glossary`. The two scripts
share the `glossary` package but never call each other: `build-glossary` always writes
`term_ru = NULL` on every entry it upserts (even on a rebuild — a stale prior
translation must not survive a re-extraction of the same block); `translate-glossary-terms`
independently and idempotently fills `term_ru` in batches, retryable forever on
`term_ru IS NULL`, and never touches extraction, embedding, or `definition`. Only
`GlossaryTermUpdateRepository` (owned by the translation side) ever writes a non-null
`term_ru` — enforced by which repository has write access to that column, not by a
database constraint. Both scripts share the same per-unit failure-isolation shape (one
block or one batch failing doesn't abort its siblings — see each script's own
`GlossaryBuildError`/`GlossaryTranslationError`), but as two independent processes with
two independent failure surfaces.

## Alternatives considered

- **Storing a full Russian translation (definition, summary) per glossary entry**:
  rejected — nothing downstream would ever read a full translated definition; only the
  term itself needs a pre-agreed rendering, consumed as a hint by the existing
  message-level translator (spec 0018). This also drops two of the three
  originally-proposed translation columns and their per-entry batching entirely.
- **Translating the term as a second field on `GlossaryExtractorAgent`'s own response**,
  in the same LLM call as extraction: rejected — the two tasks need different
  validators (verbatim-substring matching is meaningless for a translation, which by
  definition is not the same string in the source text; translation instead needs a
  simple batch-count match) and have different failure semantics (a translation failure
  should never discard an otherwise-valid, already-verbatim-validated extraction, since
  the definition and its embedding don't need `term_ru` at all).
- **Translating each term as a step inside `build-glossary`'s own per-block pipeline**,
  as a separate agent call but still within the same run: rejected in the 2026-09-24
  grilling round for the reason in Context above — `build-glossary`'s per-block
  failure-isolation contract must stay about extraction/embedding/write, not be widened
  to also cover a translation call it doesn't actually need to succeed.

## Consequences

`term_ru` can lag `definition`/`embedding` indefinitely with no correctness impact on
anything that depends on the glossary for grounding — a fresh `build-glossary` run
populates a fully usable glossary with every `term_ru` null, and spec 0020's consumers
already tolerate a null `term_ru` end to end (companion infra plan, `glossary_entries.term_ru`
made nullable). The cost is operational, not correctness: two scripts must both be run
(and re-run) to keep the glossary fully hint-populated, and there is no single command
that guarantees both extraction and translation are current at the same moment — an
operator who runs only `build-glossary` after a corpus change will see `term_ru` reset
to null for every rebuilt entry until `translate-glossary-terms` is run again
separately. This is the accepted trade — `build-glossary`'s reliability was judged more
important than translation coverage always being in lockstep with it.
