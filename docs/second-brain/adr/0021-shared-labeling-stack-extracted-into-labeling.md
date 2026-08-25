# ADR 0021: The Shared Labeling/Judge Stack Is Extracted Into a New Top-Level `src/labeling/` Package

## Status

Proposed

## Context

ADR 0013 deliberately placed the golden-set labeling machinery
(`CommaLabelerAgent`, `CandidateSetService`, `QuestionLexemeService`,
`GoldenSetWriteRepository`, `CandidateComma`, and their supporting config/
mappers) inside `src/retrieval_evaluation/` and defended that placement on the
grounds that the module is exploratory measurement instrumentation: no
manifest, no `RunArtifactWriter`, no dry-run chain, re-run by hand rather than
scheduled — deliberately outside both `ingest evaluate retrieval`'s harness and
the `ingest` CLI's audited-run-artifact machinery.

Spec 0012 (`docs/superpowers/specs/2026-08-24-quiz-flow-api-design.md`, AD-12)
adds a live judge: the future FastAPI quiz-check endpoint calls the same
comma-labeling logic synchronously, per request, to serve a user. At that
point ADR 0013's premise stops holding for this code specifically — it is no
longer measurement instrumentation, it is production request-serving logic —
but the deeper problem is not naming. It is **cache coherence**: the batch
labeler and the live judge write to the same `labeling_runs`/`quiz_labelings`/
`quiz_comma_labels` tables, keyed by a `prompt_version` that is a hash of the
loaded prompt text (AD-11, no human-maintained version field). If the batch
and live code paths diverge by even one prompt sentence, phrasing choice, or
candidate-set construction detail, `prompt_version` stops identifying a single
behaviour: two different judges start writing rows under one label, and the
cache silently mixes verdicts from implementations that were never validated
against each other. The only way to guarantee they can't diverge is for them
to *be* the same code, not two independently-maintained copies that happen to
agree today.

`src/retrieval_evaluation/` cannot be that shared home unchanged: it still
holds `retrieval_judge/` (the separate, non-persisting spot-check judge ADR
0013 introduced) and `main.py`'s harness-adjacent script shape, neither of
which the future FastAPI app should depend on, and depending on a package
literally named "evaluation" from production request-serving code would
misdescribe what the code does with every passing month.

This is quiz-flow-api-phase1 plan Task 5 (spec 0012, AD-12).

## Decision

Extract the shared labeling machinery into a new top-level package,
`src/labeling/`, a sibling of `retrieval_evaluation/`, `parsers/`, `scrapers/`
and `commons/` — not a subpackage of `retrieval_evaluation/` or `commons/`:

- `labeling/agents/comma_labeler/` — `CommaLabelerAgent` and its `dto/`
  (`CommaLabelerRequest`/`CommaLabelerResponse`), moved unchanged via `git mv`.
- `labeling/services/` — `QuestionLexemeService`, `CandidateSetService`,
  `GoldenSetLabelingService` (the pass driver).
- `labeling/repositories/golden_set_write_repository.py` —
  `GoldenSetWriteRepository`, insert-only (AD-10).
- `labeling/models/` — `CandidateComma`, `LabelingEpoch` (ADR 0020's
  companion concept, materialising the six-input configuration epoch — see
  `docs/second-brain/glossary.md`).
- `labeling/mappers/` — `LabelingEpochMapper`, `LabelingRunMapper`.
- `labeling/configs/labeling_config.py` — `LabelingConfig`, moved out of
  `guidami_ai_patente_ingestor/configs/` in the same task and extended with
  `agents_dir` (ADR 0020/AD-27).
- `labeling/utils/run_provenance.py` — `prompt_version` hashing.
- `labeling/wiring.py` — every DI builder both `retrieval_evaluation/main.py`
  and `label_main.py` need that isn't judge-specific
  (`build_open_router_provider`, `build_postgres_client`, `build_tracker`,
  `build_corpus_repository`, `build_quiz_repository`, and the labeling-only
  builders), so neither script keeps a duplicated `_build_*` set.

`src/retrieval_evaluation/` keeps only what is genuinely evaluation-specific
and not shared with a live request path: `agents/retrieval_judge/` (the
separate spot-check judge, never called from production), `models/
retrieval_judge_item_result.py`, `services/retrieval_judge_evaluation_service.py`,
`main.py` (the `evaluate-retrieval-judge` entry point), `label_main.py` (the
`label-golden-set` entry point — the script stays here since it is still a
by-hand-run batch script, only its collaborators moved), and a `wiring.py`
trimmed to the one builder that is judge-specific,
`build_retrieval_judge_agent`. `QuizEvaluationRow` (the read-model row type
consumed by both the judge and the labeler) is deliberately **not** renamed or
moved as part of this extraction — it names a retrieval-evaluation read
projection, not labeling machinery, and moving it would be an unrelated
rename riding on this refactor.

`src/labeling/` has no `pywire` import and no dependency on
`retrieval_evaluation` or `guidami_ai_patente` (the FastAPI app) — enforced by
`tests/labeling/test_module_boundary.py`'s `ast`-based import-boundary
assertions (spec 0012 Task 5), the same pattern ADR 0013's module already used
for its own "no private ingestor import" rule. `src/domain/` importing back
from `labeling/` is asserted absent in the same test file, protecting the
`lexeme_fields` canonicalisation rule's single implementation (`src/domain/`,
D8/D13) from acquiring a second, `labeling`-local copy.

## Alternatives considered

- **Leave the machinery in `src/retrieval_evaluation/` and have the future
  FastAPI app import it unchanged** — zero refactor cost today, but production
  request-serving code would permanently depend on a package named
  "evaluation", the cost of untangling the two concerns only grows with every
  future call site, and nothing would structurally prevent the batch and live
  code paths from drifting apart under separate maintenance.
- **Promote the machinery into `commons/`** — `commons/` already hosts
  `BaseAgent`, the embedding composition layer and `PostgresClient`, so it is
  an obvious place to look; rejected because `commons/` is deliberately
  generic, domain-agnostic infrastructure (ADR 0013's own rejection of this
  option for the original module), and comma labeling is domain logic about
  commas, quizzes and the corpus normativo, not infrastructure.
- **A subpackage of `retrieval_evaluation/`** (e.g.
  `retrieval_evaluation/shared/`) instead of a new top-level sibling —
  rejected: it would still force the future app to depend on the
  `retrieval_evaluation` package name and its `__init__.py`/wiring surface to
  reach the shared code, reintroducing the same naming and coupling problem
  one level down.

## Consequences

- The batch labeler (`label-golden-set`) and the future live judge share one
  implementation of every judge-identity-relevant piece (prompt, candidate-set
  construction, lexeme extraction, epoch computation) by construction — a
  divergence would require editing `src/labeling/` itself, which both callers
  see, rather than two independently-evolving copies quietly disagreeing.
- `src/retrieval_evaluation/` shrinks to what ADR 0013 originally described:
  the standalone spot-check judge and the two script entry points, now
  depending on `labeling/wiring.py` for every collaborator that isn't
  judge-specific rather than owning private `_build_*` duplicates.
- `src/labeling/` becomes a new dependency edge every future consumer of the
  golden-set labeling logic (batch or live) must cross; its import-boundary
  test is the mechanism that keeps that edge one-directional (`labeling/` may
  depend on `domain/`, never the reverse) and keeps it from acquiring a
  `pywire` or `retrieval_evaluation` dependency by accident as new code is
  added.
- ADR 0013's Context/Consequences remain the historical record of why the
  *original* module was placed outside the CLI and the `ingest evaluate
  retrieval` harness — that reasoning is unaffected by this extraction, which
  only moves the sub-slice of that module that a second, production caller
  now needs. ADR 0013 is not superseded; this ADR amends it by narrowing what
  `src/retrieval_evaluation/` still owns.
