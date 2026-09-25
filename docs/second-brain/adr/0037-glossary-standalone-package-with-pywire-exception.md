# ADR 0037: `src/glossary/` is a standalone package, wired with pywire as a deliberate exception to the batch-package default

## Status

Proposed

## Context

Building the glossary (ADR 0036) needs a real pipeline: read parsed files, extract via
an LLM agent, embed, and write. The repository already has an established shape for
this kind of work — `guidami_ai_patente_ingestor`'s `ingest prepare|index|reset`
entities — and a second, more recent precedent: standalone script packages with their
own `[project.scripts]` entry point (`labeling`, `retrieval_evaluation`,
`test_data_sampler`), none of which import each other or the ingestor.

Every existing batch-pipeline/standalone-script package in this repo uses manual
constructor injection, never `pywire`. `.claude/rules/pywire-di.md` scopes `pywire`
to `guidami_ai_patente` and the Telegram bot by default — a convention choice for those
*existing* packages (which need FastAPI-style container wiring), not a technical
limitation of the `pywire` container itself.

## Decision

The glossary pipeline is a new top-level package, `src/glossary/`, depending only on
`commons` and `domain` — never on `guidami_ai_patente_ingestor`, `labeling` or
`guidami_ai_patente`. It hosts its own two `[project.scripts]` entry points
(`build-glossary`, `translate-glossary-terms`), each with its own `main.py`, mirroring
`labeling`'s standalone-script shape rather than becoming a new `ingest` subcommand.

Unlike every other batch package in the repo, `glossary` is wired with `pywire` field
injection (`Autowired[T]`) throughout its own agents/services/repositories — a narrow,
explicit exception to the batch-package default, recorded in `.claude/rules/pywire-di.md`
itself, not just in this ADR. `GlossaryConfig` and the handful of `commons` primitives
`pywire` has no constructor recipe for (`PostgresClient`, `EmbeddingService`, the
OpenRouter provider, `LlmCallTracker`) are built once in each entry point's `main()`/
`translate_main()` and registered via `container.register_instance`, never autowired as
if they built themselves — the same treatment `AppConfig` gets in `guidami_ai_patente`.

## Alternatives considered

- **New `ingest prepare|index|reset glossary` entities**, hosting the glossary inside
  `guidami_ai_patente_ingestor`: rejected — the glossary is a self-contained derived
  asset (ADR 0036), and hosting it in the ingestor would couple it to the ingestor's
  CLI, its config root (`IngestorConfig`), its layer/status/reset machinery and its
  `--dry-run`/manifest conventions, all designed around the corpus and quiz lifecycles
  this feature has nothing to do with.
- **Manual constructor injection, matching every other batch package** (`labeling`,
  `retrieval_evaluation`, `guidami_ai_patente_ingestor`): considered as the "do what
  the rest of the codebase does" default, but rejected for this specific package —
  `glossary`'s own agent/service/repository graph benefits from field injection the
  same way `guidami_ai_patente`'s does (it mirrors `ExplanationTranslatorAgent`'s
  three-`Autowired` shape almost verbatim), and critically, `glossary` never imports,
  and is never imported by, `labeling` or `retrieval_evaluation` — so there is no
  shared-default-container collision risk to design around, unlike the
  bot/API `QuizApiClient` case `pywire-di.md` already documents. This is a decision
  about `glossary` specifically; it does not imply `labeling`/`retrieval_evaluation`/
  the ingestor should be migrated to `pywire` too — that remains a separate, larger,
  not-yet-made decision.

## Consequences

A future contributor reading `glossary/` sees a DI style (`pywire`) different from every
sibling batch package (`labeling`, `retrieval_evaluation`, the ingestor), which could
read as inconsistency without this ADR's context — the exception is intentional and
narrow, not a sign the rest of the codebase is migrating. Testing follows a different
idiom too: `glossary`'s pure-unit tests bypass the container via
`ClassName.__new__(ClassName)` plus manual `Autowired`-field assignment (the same
pattern `docs/second-brain/testing.md` already documents for `guidami_ai_patente`), not
the plain constructor calls manual-DI packages use. The package gains real reuse of
`pywire`'s field-injection ergonomics without inheriting the API/bot's shared-container
collision risks, since `glossary` sits in its own import graph entirely.
