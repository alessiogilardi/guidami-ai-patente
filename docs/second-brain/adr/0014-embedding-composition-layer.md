# ADR 0014: Generic Composition Layer for Embedding, `EmbedQuizVariantsService` as a Thin Adapter

## Status

Rejected — see "Rejection" section at the end of this document.

## Context

`commons/ai/embedding/` originally held only `clients/` (provider adapters),
`configs/` (`EmbeddingConfig`), and `services/` (`EmbeddingService`, taking
`Sequence[str]` directly since spec 0008 Phase 2's AD-9). Two production
consumers built their own text-composition logic directly on top of it:

- `EmbedCommasStep` extracted `comma.embedded_text` via a list comprehension
  and called `EmbeddingService` with the resulting strings — a clean 1:1
  case (one comma, one text, one vector).
- `EmbedQuizVariantsService._embed_variant` was structurally different: for
  each of N registered `QuizVariantSpec` entries (`services/quiz/
  quiz_variant_registry.py`, AD-7), it built a text per item (`text_builder`,
  returning `None` to signal "this item has no input for this variant" —
  counted, never a stored null vector, AD-2/FR-2), deduplicated items sharing
  a `dedup_key` (AD-8 — e.g. several questions sharing one road-sign image),
  called `EmbeddingService` once per variant on the deduplicated texts, then
  fanned the resulting vector back out to every item in each dedup group.

A separate, independently landed piece of work introduced a generic
composition layer for the 1:1 case: `TextComposer[T]` (a structural
protocol, `compose(model: T) -> str`), three implementations
(`FieldSpecComposer[T]`, `TemplateComposer[T]`, `CallableComposer[T]`), and
`ModelEmbeddingService[T]` (composes + embeds a batch of models 1:1,
delegating chunking to the existing `EmbeddingService`).

The user then asked for both production consumers to be migrated onto this
new layer, deleting whatever became obsolete. `EmbedCommasStep` migrates
directly — `CallableComposer(operator.attrgetter("embedded_text"))` is
exactly a `TextComposer[EmbeddableArticleComma]`. `EmbedQuizVariantsService`
does not: `TextComposer[T].compose(model) -> str` is a pure 1:1 mapping and
expresses neither per-variant omission nor dedup-by-key. Forcing it onto
`ModelEmbeddingService[T]` unchanged would mean either losing the dedup (one
embedding call per item instead of per distinct text — real added cost on a
metered provider) or reimplementing the grouping logic outside the
composition layer, which would not actually be "using the new pattern," only
wrapping the same bespoke logic in new clothing.

Two structural questions had to be resolved before writing any code:

1. Is the dedup/omission/fan-out mechanics genuinely quiz-specific domain
   logic, or a generic shape worth generalizing?
2. If generalized, does `EmbedQuizVariantsService` still exist afterward, and
   in what form? Does the existing `QuizVariantSpec` `NamedTuple` still exist?

On (1): nothing in `_embed_variant`'s logic references quiz concepts by
name — it is "N named text representations of one model type, each with its
own per-item omission rule and dedup key," parametrized entirely by the
injected `VariantSpec[T]` values. The quiz registry is the *only* current
caller, but the shape is domain-agnostic the same way `ModelEmbeddingService`
already is.

On (2): the user, asked directly, chose to keep `EmbedQuizVariantsService`
as a thin domain adapter (not delete it and wire the generic service
directly in `quiz_flows.py`) — this preserves `EmbedQuizVariantsService`'s
public constructor, its `KeyError`-on-unknown-variant startup check, and the
persisted `EmbeddableQuizVariant`/`EmbedQuizVariantsResult` DTO shape
`StoreQuizStep`/`QuizQuestionEmbeddingStoreRepository` require (fixed DB
columns: `quiz_question_id`, `variant`, `embedding_3_small`), with zero
wiring changes in `quiz_flows.py`. The user also chose, asked directly, to
delete `QuizVariantSpec` (a `NamedTuple` with `Callable` fields, never
carrying the documented justification `.claude/rules/code-conventions.md`
requires for a `NamedTuple` over a `dataclass`) in favor of the new generic
`VariantSpec[T]` dataclass, used directly in `QUIZ_VARIANT_REGISTRY`.

## Decision

`commons/ai/embedding/` gains a **sixth** subpackage, `composition/` (beyond
the five-subpackage-by-responsibility shape `docs/second-brain/layout.md` documents for
`commons/ai/`), plus new `models/` and a new `services/` member:

- `protocols/text_composer.py::TextComposer[T]` — `compose(model: T) -> str`.
- `models/{field_spec,embedding_spec,embedding_result}.py` — the 1:1
  composition recipe and result triple.
- `models/{variant_spec,variant_embedding_row,variant_embedding_result}.py` —
  `VariantSpec[T]` (`name`, `text_builder: T -> str | None`,
  `dedup_key: T -> str`, no default — a generic default can't assume a
  natural key over an arbitrary `T`), `VariantEmbeddingRow[T]`
  (`model`/`variant`/`embedding`), `VariantEmbeddingResult[T]`
  (`rows`/`omitted_counts`).
- `composition/{field_spec_composer,template_composer,callable_composer}.py` —
  `FieldSpecComposer[T]`, `TemplateComposer[T]`, `CallableComposer[T]`, all
  implementing `TextComposer[T]` structurally.
- `services/model_embedding_service.py::ModelEmbeddingService[T]` — 1:1
  composition + embedding.
- `services/variant_model_embedding_service.py::VariantModelEmbeddingService[T]` —
  the generalized `_embed_variant` mechanics: for each `VariantSpec[T]`,
  build texts (counting omissions), group by `dedup_key`, embed each
  group's first-item text once, fan the vector back out.

`EmbedCommasStep` is migrated: its constructor now takes a
`ModelEmbeddingService[EmbeddableArticleComma]` (wired with
`CallableComposer(operator.attrgetter("embedded_text"))`) instead of an
`EmbeddingService` directly; `EmbeddableArticleComma.embedded_text` itself is
unchanged.

`EmbedQuizVariantsService` is reduced to a thin adapter: its constructor
resolves `enabled_variants` against `QUIZ_VARIANT_REGISTRY` (now
`Mapping[str, VariantSpec[EmbeddedQuizModel]]`) into a
`VariantModelEmbeddingService[EmbeddedQuizModel]`, and `execute` remaps its
`VariantEmbeddingRow` output onto `EmbeddableQuizVariant`. Public
constructor signature, `KeyError`-on-unknown-variant behavior, and
`EmbedQuizVariantsResult` shape are all unchanged. `quiz_flows.py`'s wiring
is unchanged. `QuizVariantSpec` is deleted.

Every `UseCase` in the codebase — this generalization included — is now
invoked via `__call__`, never `.execute()` directly
(`.claude/rules/use-case-invocation.md`, a companion convention landed in
the same round of work).

## Alternatives considered

- **Leave `EmbedQuizVariantsService` untouched, migrate only
  `EmbedCommasStep`.** Rejected on explicit user instruction: the request
  was for *only* the new pattern to remain, with obsolete code deleted, not
  a partial migration that leaves two competing embedding-consumption styles
  in the ingestor.
- **Force `EmbedQuizVariantsService` onto `ModelEmbeddingService[T]`
  unchanged, dropping dedup.** Rejected — it would call the embedding
  provider once per item instead of once per distinct text within a variant,
  a real, avoidable cost increase on a metered API, for no benefit.
- **Eliminate `EmbedQuizVariantsService` entirely, wire
  `VariantModelEmbeddingService[EmbeddedQuizModel]` directly in
  `quiz_flows.py`, add a separate mapper for the DTO conversion.** Rejected,
  asked directly: `StoreQuizStep` genuinely needs the persisted
  `EmbeddableQuizVariant`/`EmbedQuizVariantsResult` shape (fixed DB columns),
  so a domain-facing adapter is doing real work, not just forwarding; keeping
  it means zero change to `quiz_flows.py`'s wiring and to the DTOs
  `StoreQuizStep` depends on.
- **Keep `QuizVariantSpec` as a local alias/wrapper around
  `VariantSpec[EmbeddedQuizModel]`.** Rejected, asked directly: it would add
  a type and a file with no behavioral difference from the generic type it
  wraps — the exact kind of unnecessary abstraction the project's standards
  discourage.
- **Add `tracker()`/composer behavior as methods on existing protocols
  instead of free functions/classes** (a related decision made in the same
  round of work, for `commons.observability.progress_reporter.tracker`) —
  rejected because `ItemProgressReporter` already has two independent
  concrete implementations (`NullProgressReporter`, `LiveDashboard`) that
  don't share a common base, so a method would have to be duplicated in
  both; a free function works with any structurally-compatible reporter.
  Noted here for completeness since it shaped the sibling `tracker.py`
  addition in the same commit as this composition layer, even though it
  lives in `commons/observability/`, not `commons/ai/embedding/`.

## Consequences

- `commons/ai/embedding/` now has six subpackages instead of the
  five-subpackage-by-responsibility shape `docs/second-brain/layout.md` documents for
  `commons/ai/agents`/`commons/observability/` — an intentional, narrowly
  justified deviation (`composition/` holds classes that are neither
  services nor static mappers), not a precedent for every future package to
  add ad hoc subpackages.
- The dedup/omission/fan-out mechanics that used to be quiz-only test
  surface (`tests/.../services/quiz/test_embed_quiz_variants.py`) now has a
  domain-agnostic test suite in `commons/`
  (`tests/commons/ai/embedding/services/test_variant_model_embedding_service.py`)
  plus a thin adapter-level test verifying `EmbedQuizVariantsService` still
  produces the right DTOs — a small duplication of coverage at the boundary,
  accepted since the adapter's own mapping logic (not just delegation) is
  worth testing directly.
- `VariantSpec[T].dedup_key` has no default, unlike the deleted
  `QuizVariantSpec.dedup_key`'s `item.number` default — every
  `QUIZ_VARIANT_REGISTRY` entry must now state it explicitly (a
  `_dedup_by_number` helper for the five per-question variants). Slightly
  more verbose at the one current call site, in exchange for never silently
  assuming an identity function that doesn't exist for an arbitrary `T`.
- No other consumer of the composition layer exists yet — `VariantModelEmbeddingService[T]`
  is generalized ahead of a second real caller, on the strength of the shape
  already being domain-agnostic in the code it was extracted from, not
  because a second caller is planned.

## Rejection

This ADR's implementation was never completed (the working tree it landed
in had `commons/ai/embedding/models/__init__.py` and `services/__init__.py`
already importing `variant_spec.py`/`variant_embedding_row.py`/
`variant_embedding_result.py`/`variant_model_embedding_service.py`, but none
of those four files existed — `commons.ai.embedding` was left unimportable).
Asked directly, in the same session that discovered this, the user rejected
the Decision above: `VariantSpec[T]`/`VariantEmbeddingRow[T]`/
`VariantEmbeddingResult[T]`/`VariantModelEmbeddingService[T]` are **not**
built. The dedup/omission/fan-out mechanics stay domain logic local to
`guidami_ai_patente_ingestor/services/quiz/` (`quiz_variant_registry.py` +
new `quiz_variant_spec.py`), never generalized into `commons/`.

The underlying problem — express "this text representation may legitimately
not exist for this model" declaratively — was still real, so a much smaller
extension was made instead of the rejected generalization:

- `commons/ai/embedding/protocols/optional_text_composer.py::
  OptionalTextComposer[T]` (`compose_or_none(model: T) -> str | None`), the
  counterpart of the existing `TextComposer[T]` (`compose(model: T) -> str`)
  for a representation that may be absent — a distinct method name, not an
  overload of `compose`, so one class can implement both protocols at once.
  `TextComposer[T]` itself is unchanged — widening it to `str | None` would
  have forced a needless `None`-check onto `ModelEmbeddingService[T]`'s 1:1
  pipeline (`EmbeddingResult.text: str`, not Optional), which never has this
  problem.
- `FieldSpec.from_attr` gained a `skip_if_none` parameter, so a "required"
  field can still be declared without hand-writing a `FieldSpec(...)` call.
- `FieldSpecComposer` gained a second method, `compose_or_none`, alongside
  the unchanged `compose` (`-> str`): `compose_or_none` returns `None` when
  any field marked `skip_if_none=False` ("required") extracts to `None`,
  instead of silently dropping just that field or (as `compose` still does)
  rendering it as literal `"None"` text. The check is unconditional — no
  extra spec-level flag was needed once the two methods were split apart
  (an earlier draft of this fix added `EmbeddingSpec.skip_if_any_none` for
  this, then removed it once `compose_or_none` existed as its own method,
  since the flag became redundant with it). `FieldSpecComposer` now
  implements **both** `TextComposer[T]` and `OptionalTextComposer[T]` —
  the caller picks whichever method its pipeline needs, with no wrapper.

`QuizVariantSpec` is **not** deleted (contrary to this ADR's Decision): it
is kept as a local `services/quiz/quiz_variant_spec.py` frozen `dataclass`
(justified per `.claude/rules/code-conventions.md` by its `Callable`
`dedup_key` field, same reasoning this ADR already used for the generic
`VariantSpec[T]`), now typed with
`text_composer: OptionalTextComposer[EmbeddedQuizModel]`. Every entry in
`QUIZ_VARIANT_REGISTRY` is a `FieldSpecComposer` wrapping a declarative
`EmbeddingSpec`/`FieldSpec` recipe — the composition layer is reused, only
the N-variant/dedup/fan-out generalization is not. See `docs/second-brain/architecture.md`,
`docs/second-brain/patterns.md`, and `docs/second-brain/glossary.md` for the resulting (accurate)
description of `commons/ai/embedding/` and the quiz-variant registry.
