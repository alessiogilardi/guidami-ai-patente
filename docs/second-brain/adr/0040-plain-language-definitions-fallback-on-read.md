# ADR 0040: Plain-language glossary definitions as a second decoupled script and a read-side fallback, never a rewrite of `definition`

## Status

Proposed

## Context

`glossary_entries.definition` (spec 0019) is extracted verbatim from the corpus under
ADR 0038's mechanical guarantee — by design, unedited normative legal text. That text is
exactly what makes it trustworthy as RAG grounding (it is what `embedding_3_small`
embeds, and what `QuestionExplainerRequest.candidates_block` feeds to
`QuestionExplainerAgent`'s prompt) and exactly what makes it opaque to an end user: CdS/CAP
definitions are dense legalese, and `ExplanationService._deduplicated_hints` was copying
that same verbatim text onto every `CitedGlossaryTerm`/`CitedGlossaryTermResponse` the
vocabulary stage cited — text `CitedGlossaryTermResponse`'s own docstring confirms is
"rendered by the bot as its own glossary-block line", i.e. read directly by the user.

The requester's own first proposal was to keep the column named `definition` but change
what it holds (a plain-language rewrite), moving the verbatim text to a new
`definition_extracted` column. Tracing the actual consumers of `definition` — it is the
source of `embedding_3_small` (spec 0019 FR-6) and of ADR 0038's verbatim
`output_validator` guarantee — showed that renaming it would force every write-path class
that already reads/writes it (`GlossaryExtractorAgent`'s validator,
`GlossaryEntryWriteRepository`'s upsert, `GlossaryBuildService`'s embedding step) to be
repointed at a differently-named column, for no functional gain: the "consumers don't
change" goal the requester actually wanted is achievable without ever touching that
already-validated write path (see Decision).

Spec 0019/ADR 0039 already answered a structurally identical question for `term_ru`: a
derived column, filled independently, by a script decoupled from `build-glossary`, with
the read side tolerating `NULL`. This spec's decision is that same shape, reused for a
second derived column.

## Decision

`definition_plain` is a new, separate, nullable column on `glossary_entries` —
`definition` itself is never renamed, rewritten, or repointed. It is filled by a third,
independent, decoupled script, `simplify-glossary-definitions`
(`glossary.simplify_main:main`), which mirrors `translate-glossary-terms`'s exact shape:
its own agent (`GlossaryDefinitionSimplifierAgent`), its own read/update repositories
(`GlossaryDefinitionReadRepository`/`GlossaryDefinitionUpdateRepository` — the latter the
only class that ever writes `definition_plain`), and its own run service
(`GlossaryDefinitionSimplificationRunService`) with the same per-batch
failure-isolation shape (`GlossaryDefinitionSimplificationError`). `build-glossary` always
writes `definition_plain = NULL` on insert and now also resets it to `NULL` on every
upsert conflict — a one-line addition to `GlossaryEntryWriteRepository`'s existing `SET`
clause, found during a `mattpocock-skills:grilling` stress-test round on the written spec
(not the original brainstorming pass): without that reset, a `--force` rebuild that
changes a block's verbatim text would silently leave the *old* plain-language rendering in
place forever, since `simplify-glossary-definitions` only ever selects rows where
`definition_plain IS NULL`.

`GlossaryDefinitionSimplifierAgent`'s `output_validator` deliberately does **not** check
verbatim fidelity — the opposite invariant from `GlossaryExtractorAgent` (ADR 0038):
rewriting the legal text into plain Italian is its entire job. It only rejects a batch
whose response count doesn't match the input batch's, plus a plain `Field(min_length=1,
max_length=400)` bound on each rewritten sentence.

On the read side, `GlossaryCandidate` gains `definition_plain: str | None = None`
(default preserves every pre-existing construction call site). The **only** consumer is
`ExplanationService._deduplicated_hints`, which builds `CitedGlossaryTerm.definition`
from `candidate.definition_plain or candidate.definition` — preferring the plain
rendering, falling back to verbatim when a row hasn't been simplified yet. No
`WHERE definition_plain IS NOT NULL` filter exists anywhere, and there is no required run
order between `build-glossary` and `simplify-glossary-definitions` — the same
fallback-on-read shape ADR 0039 established for `term_ru`, reused unchanged for a second
derived column. `QuestionExplainerRequest.candidates_block` (the LLM grounding prompt)
still reads verbatim `definition` — grounding fidelity for the model is worth more than
register consistency between what the model reads and what the user reads.
`CitedGlossaryTerm`, `CitedGlossaryTermResponse`, `ExplanationMapper`, and the bot's own
model all gain no new field: the wire contract of `GET .../explanation` is unchanged.

## Alternatives considered

- **Swap column semantics** (the requester's own first proposal): keep the name
  `definition`, change it to hold plain text, and rename the verbatim column to
  `definition_extracted`. Rejected once the actual consumers were traced (Context above)
  — it achieves the same "consumers don't change" goal as this decision, but only by
  touching the write path and embedding source spec 0019/ADR 0038 already validated, for
  no functional gain.
- **A third column consumed everywhere, including the explainer's own grounding
  prompt**: rejected — `QuestionExplainerRequest.candidates_block` feeds the LLM's own
  prompt, and grounding fidelity there is worth more than register consistency between
  the model's input and the user's output.
- **Folding simplification into `build-glossary`'s own pipeline**, as a step right after
  extraction in the same run: rejected for the identical reason ADR 0039 gives for
  `term_ru` — a simplification failure must never fail, retry, or block an extraction
  that has nothing to do with it. `build-glossary`'s failure-isolation contract stays
  about extraction/embedding/write only.
- **Excluding a term from the API response until it has a plain rendering** (a
  `WHERE definition_plain IS NOT NULL` filter, or gating the vocabulary stage on it):
  rejected — `term_ru` already established that a `glossary_entries` row is complete and
  servable the moment `build-glossary` writes it, with a derived column filled in later
  and possibly never, without that ever making the row unservable (ADR 0039). Gating on
  write would also impose a run-order dependency between the two independent scripts that
  nothing else in the design requires.

## Consequences

`definition_plain` can lag `definition`/`embedding_3_small` indefinitely with no
correctness impact on retrieval or grounding — a fresh `build-glossary` run populates a
fully usable, gradeable glossary with every `definition_plain` null, and the vocabulary
stage already tolerates that (falling back to verbatim text, exactly as today, for every
row not yet simplified). The cost is operational, not correctness: two scripts
(`build-glossary` and `simplify-glossary-definitions`) must both be run — and, after any
`--force` rebuild, re-run — to keep the glossary's user-facing text fully plain-language;
there is no single command guaranteeing both are current at the same moment. An operator
who runs only `build-glossary --force` after a corpus/parser change will see every
rebuilt row's `definition_plain` reset to `NULL` (and its user-facing text silently
revert to verbatim legalese) until `simplify-glossary-definitions` is run again
separately. This mirrors `term_ru`'s already-accepted trade-off (ADR 0039) exactly, one
column over.
