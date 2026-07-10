# Patterns and Conventions

Enforceable rules (typing, DI ordering, config-loading, import style) live
in `~/.claude/rules/python/` and `.claude/rules/`. This file only records
recurring idioms actually adopted in the code, as a reference for reuse —
it does not restate those rules.

## Adopted patterns

| Pattern | Where it's used | Why |
|---|---|---|
| `UseCase[T_In, T_Out]` / `AsyncUseCase` protocol | `src/commons/use_cases/use_case.py` — `__call__` is `@final`, delegates to abstract `execute()` | Uniform callable contract for domain logic; every business-logic unit is typed, testable, composable |
| `ForEach[T, U]` | `src/commons/use_cases/for_each.py` — a `UseCase[Iterable[T], list[U]]` wrapping a per-item callable | Turns any `UseCase`/callable into a list-mapper without per-step loop boilerplate |
| `FlatMap[T, U]` | `src/commons/use_cases/flat_map.py` — a `UseCase[Iterable[T], list[U]]` wrapping a per-item `Callable[[T], Iterable[U]]`, concatenating results | One-to-many transforms (one input produces N outputs); e.g. `ApplyStep("chunk_articles", FlatMap(ArticleChunker(source)), ...)` in `orchestrators/knowledge_flows.py` and `ApplyStep("flatten_quiz", FlatMap(QuizMapper.from_parsed_to_cleaned_all), DeduplicateQuizItems(), ...)` in `orchestrators/quiz_flows.py` |
| `ApplyStep(ForEach(...))` composition | `orchestrators/knowledge_flows.py` — e.g. `ApplyStep("map_to_chunk_entity", ForEach(ArticleMapper.from_embeddable_chunk_to_knowledge_chunk), ...)`; also combined with `ContextEnricher(agent)` in one `ApplyStep` | Standard glue between the domain-agnostic `flowstep` framework (external git dependency, see `docs/architecture.md`) and per-item domain transforms/mappers |
| `Iterable[T]`-typed `ApplyStep` transforms | All `UseCase` subclasses passed as `ApplyStep(...)` transforms (`ForEach`, `FlatMap`, `DeduplicateQuizItems`, `EmbedQuizMetadata`, `ImageDescriptionEnricher`, `NormReferenceEnricher`, `ContextEnricher`) declare `execute(self, request: Iterable[T]) -> list[U]` | `flowstep`'s `ApplyStep` (external dependency) types transforms as `Callable[[Iterable[Any]], Iterable[Any]]`; a `list[T]`-only parameter fails pyright. Transforms that traverse `request` more than once materialize it first (`request = list(request)`) since `Iterable` doesn't guarantee re-iterability |
| Dedup-before-LLM enricher via `deduplicate` | `services/quiz/enrichers/image_description_enricher.py` and `norm_reference_enricher.py` — build a `dict[key, response]` by mapping `commons.utils.deduplicate(items, key=_make_key)` through the agent, then broadcast each response to every row sharing the key | One LLM call per unique key (e.g. `(image, topic, text)`) instead of per row; the order-preserving `deduplicate` pass replaces manual `seen`-set bookkeeping |
| `embedded_text` computed property | `models/knowledge/embeddable_chunk.py`, `models/quiz/embeddable_quiz.py` (delegates to `quiz_metadata.embedded_text`) | Single source of truth for "what text gets embedded", decoupled from the persisted entity's fields |
| `embed_repealed` config flag | `configs/ingestor_config.py` (default `False`), consumed by `orchestrators/steps/knowledge/embed_chunks_step.py` | Lets repealed norms be indexed or excluded without a schema/pipeline change |
| `BaseAgent[T_In, T_Out]` + `PromptRenderer` | `src/commons/agents/base_agent.py` (wraps `pydantic_ai.Agent`, `from_yaml` factory, `run`/`run_sync`/`__call__`); concrete agents like `RoadSignDescriberAgent` only override `from_yaml` for typed construction | Shared LLM plumbing (config load, prompt rendering, retries); per-agent code reduces to typing + prompt file |
| Repository with scoped reset (`*StoreRepository`) | `repositories/db/knowledge_chunk_store_repository.py` extends `BulkInsertStoreRepository[KnowledgeChunk]`, adds `delete_source` alongside the inherited `truncate` | Two reset strategies for two different CLI flows: `ingest index` (per-source reload) vs `ingest reset` (full wipe) |
| Static, verbose mapper methods (`from_X_to_Y`) | `mappers/article_mapper.py`, `mappers/quiz_mapper.py` — all methods static and pure, one pure function per pipeline-stage transform | Confirmed convention: mappers are static utility classes, never DI-injected (see also `feedback_mappers_static_verbose` memory) |
| Config loaded once at entry point | `cli.py` — `IngestorConfig()` constructed inside `main()`, then passed down into every `build_*_flow(config=..., ...)` call | Matches the global rule: root config loaded in `main`, never inside builders/services |

**Naming discrepancy** (worth knowing, not "wrong"): the global
architecture rule (`~/.claude/rules/python/architecture.md`) calls for
`*Pipeline`/`*PipelineBuilder` classes in `orchestrators/`. In this repo,
`orchestrators/knowledge_flows.py` and `quiz_flows.py` instead use
**factory functions** returning a `flowstep.Flow`
(`build_knowledge_indexing_flow`, `build_quiz_cleaning_flow`, etc.) — the
`flowstep` framework's own vocabulary (`Flow`/`FlowBuilder`) replaces the
`*Pipeline`/`*PipelineBuilder` naming here. Follow this file's precedent
in `orchestrators/`, not the generic rule's literal class names.

`MapStep`, `EnrichDataStep`, and `EnricherProtocol` were removed from the
codebase (per the legacy architecture docs) — confirmed gone from `src/`.
Stale references to them survive only as outdated comments in
`orchestrators/context_keys.py`; don't use them as a model for new code.

## Naming conventions

- Suffix-per-role: `*Step` (flowstep steps), `*Service`/`*Enricher`
  (domain logic), `*Repository`, `*Client`, `*Mapper`, `*Agent`, `*Config`.
- Flow factory functions: `build_<domain>_<stage>_flow` (e.g.
  `build_knowledge_indexing_flow`, `build_quiz_cleaning_flow`).
- `UseCase`-implementing collaborators are stored on `self` named after
  what they *are* (e.g. `self._agent`), never `self._use_case` — see
  `feedback_usecase_naming` memory.

*Last updated: 2026-07-10 — verified against commit `fb2f0ae`.*
