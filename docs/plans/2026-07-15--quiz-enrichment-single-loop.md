---
status: Implemented
effort: M
---
# Quiz Enrichment Single Loop

References:
- `docs/adr/0003-group-road-sign-description-by-image.md` (image enricher async design)
- `docs/patterns.md` (group-by-resource enricher; UseCase/AsyncUseCase protocol)
- `.claude/rules/logging.md` (logging levels convention)

## Context and motivation

`ingest prepare quiz --force` reliably crashes with `RuntimeError: Event loop is closed`
(surfaced as `ModelAPIError: Connection error`) during norm-reference enrichment.

Root cause: `build_quiz_enrichment_flow` shares one `OpenRouterProvider` — hence one
persistent `httpx.AsyncClient` connection pool — between two enrichers that each drive
their **own** event loop. `ImageDescriptionEnricher.execute` opens loop A via
`asyncio.run()`, pools keep-alive connections on it, then closes loop A.
`NormReferenceEnricher` then runs via `run_sync()` → `get_event_loop()` on a fresh loop B;
the first httpx-level retry that touches a connection pooled under the now-closed loop A
raises `RuntimeError: Event loop is closed`. It is deterministic given real-network
retries, not data-dependent — reproduces on essentially every run.

Fix: run the whole enrichment phase under a **single** event loop, so the shared client
never has connections reused across loops. Do this with a project-owned `AsyncApplyStep`
(an async twin of flowstep's `ApplyStep`) that owns the single `asyncio.run()` and awaits
the async enrichers sequentially. The enrichers become plain `AsyncUseCase` services with
no internal loop management.

### Affected areas

`services/quiz/enrichers/image_description_enricher.py`,
`services/quiz/enrichers/norm_reference_enricher.py`,
new `orchestrators/steps/generic/async_apply_step.py`,
`orchestrators/steps/generic/__init__.py`,
`orchestrators/context_keys.py`,
`orchestrators/quiz_flows.py` (`build_quiz_enrichment_flow`),
`configs/ingestor_config.py`,
and the corresponding unit tests.

### Success criteria

`prepare quiz --force` completes without `Event loop is closed`; norm enrichment runs
strictly after image enrichment completes (never before/concurrently); the whole
enrichment phase runs under a single `asyncio.run()`; each enricher uses `asyncio.gather`
internally within its own phase, bounded by a semaphore.

## Non-goals

- Knowledge enrichment flow (`ContextEnricher`) — it has a single enricher, no cross-loop
  reuse, so it is not affected and is not touched here.
- The broader `logging.md` enforcement sweep across other files (separate task).
- Per-run / factory client rebuilding (rejected approaches from the analysis).
- Any modification to the external `flowstep` dependency. `AsyncApplyStep` **subclasses**
  flowstep's `Step` in this repo — subclassing is not modifying the dependency.

## Decisions

1. **Single loop owned by a custom `AsyncApplyStep`, not a composite UseCase** — loop
   ownership belongs at the execution/step layer, mirroring the existing custom steps
   (`LoadJsonStep`, `WriteJsonStep`). This keeps the two enrichers as pure `AsyncUseCase`
   services and makes the async step the reusable async counterpart of flowstep's sync
   `ApplyStep`. Chosen over a composite `QuizEnricher(UseCase)` that would hide an event
   loop inside a "use case".
2. **`AsyncApplyStep` extends `Step`, not `ApplyStep`** — the transform signature differs:
   async transforms are `Callable[[Iterable], Awaitable[Iterable]]`, incompatible with
   `ApplyStep`'s sync `Callable[[Iterable], Iterable]`. Re-implementing the ~10-line
   `execute` on top of `Step` is cleaner than fighting the sync base's typing.
3. **Sequential `await` is the ordering guarantee** — `_apply_chain` does
   `for t in transforms: result = await t(result)`, so norm enrichment cannot start until
   image enrichment has fully completed. This satisfies the hard constraint that norm must
   never run before image description.
4. **Split the sync cleaned→enriched map out of the enrichment step** — the map
   (`ForEach(QuizMapper.from_cleaned_to_enriched)`) is a sync, pure transform and does not
   belong in an async step. It moves to its own sync `ApplyStep`
   (`CLEANED_QUIZ → MAPPED_QUIZ`); `AsyncApplyStep` then runs only the async enricher chain
   (`MAPPED_QUIZ → ENRICHED_QUIZ`). Adds one context key, `MAPPED_QUIZ`.
5. **Bounded norm concurrency via new config field** — add
   `norm_reference_describer_concurrency: int = 8` to `IngestorConfig`, mirroring
   `road_sign_describer_concurrency`, and pass it to `NormReferenceEnricher`. Prevents
   firing all unique-question calls at once (OpenRouter 429 risk); independently tunable
   from the image concurrency.
6. **`AsyncApplyStep` preserves data-volume observability** — it wraps `track_data_volume`
   exactly like `ApplyStep`, so the "consumed N / produced N" step logs are unchanged.
7. **Legible logging: no tracebacks on the degrade path** — the current enrichers log
   `logger.warning(..., exc_info=True)` on every per-item failure, dumping a full traceback
   to stdout and making runs illegible (this is exactly what happened in the crash we are
   fixing). New discipline for the code touched by this plan, per `.claude/rules/logging.md`:
   - **INFO** = phase milestones only, one line each with a count (e.g. "Describing N
     distinct image(s)", "Generating norm metadata for N unique question(s)"). No per-item
     INFO — `BaseAgent` already logs per call, adding per-item here would double it.
   - **WARNING** = one concise line per degraded item: the identifying key plus the
     exception's `str`, and **no `exc_info`** (no traceback in stdout).
   - **DEBUG** = the full traceback for that failure (`logger.debug(..., exc_info=True)`),
     available when debugging without polluting a normal run; plus `AsyncApplyStep`'s
     "applying N transform(s)" trace line.
   This keeps each touched module multi-level (DEBUG + INFO + WARNING), never single-level.
   - **String formatting**: every log call uses lazy `%s`/`%r`/`%d` **args**, never
     f-strings (per `.claude/rules/logging.md`, enforced by ruff `G004`). This suits the
     parallel, high-volume enrichment path: string construction is deferred until a record
     is emitted, so disabled DEBUG in the per-item hot path costs nothing. All code samples
     below already follow this.

## Open questions / Risks

- **Risk — pydantic_ai `run` vs `run_sync` under one loop**: the enrichers switch from
  `run_sync` to `await agent.run(...)`. `BaseAgent.run` already exists and is used by
  `ImageDescriptionEnricher` today, so this path is proven. Mitigated by existing tests +
  a live `prepare quiz --force` run in the DoD.
- **Risk — semaphore loop binding**: an `asyncio.Semaphore` binds to the loop of first
  use. Both enrichers must create their semaphore *inside* `execute` (per the existing
  comment in `image_description_enricher.py`), now that the loop is owned by the step.
- **Risk — test async conversion**: existing enricher tests call `enricher(...)`
  synchronously. They must become `async def` + `await` (trivial under
  `asyncio_mode = "auto"`, already configured in `pyproject.toml`).

## Implementation tasks

> Ordering: implement 1 → 6 in sequence. Tasks 2 and 3 depend on the `AsyncUseCase` base
> (already present in `commons/use_cases`). Task 6 depends on 1–5.

### 1. Add `AsyncApplyStep` generic step

Create `src/guidami_ai_patente_ingestor/orchestrators/steps/generic/async_apply_step.py`
with **exactly** this content (async twin of flowstep's `ApplyStep`; owns the single
`asyncio.run`; strictly sequential awaits):

```python
"""Generic step that applies a chain of async transforms under a single event loop.

The async twin of flowstep's ``ApplyStep``: it reads a value from the context, awaits
each async transform in sequence, and writes the result back. It owns the single
``asyncio.run`` for the whole chain, so every awaited transform shares one event loop —
avoiding cross-loop reuse of any client (e.g. a shared ``httpx.AsyncClient``) held by the
transforms. Transforms run strictly in order: transform N+1 starts only after transform N
has fully completed.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from flowstep import (
    DataVolumeObserver,
    FlowContext,
    LoggingDataVolumeObserver,
    Step,
    track_data_volume,
)

logger = logging.getLogger(__name__)


class AsyncApplyStep(Step):
    """Applies one or more async transforms (Iterable → Awaitable[Iterable]) in sequence.

    Args:
        name: Unique step name within the flow.
        *transforms: Async callables applied in order; each awaited to completion before
            the next starts.
        input_key: Context key to read the source value from.
        output_key: Context key to write the result to.
        data_volume_observer: Observer notified with consumed/produced element counts.
            Defaults to ``LoggingDataVolumeObserver()``.
    """

    def __init__(
        self,
        name: str,
        *transforms: Callable[[Iterable[Any]], Awaitable[Iterable[Any]]],
        input_key: str,
        output_key: str,
        data_volume_observer: DataVolumeObserver | None = None,
    ) -> None:
        """Injects name, async transform chain, input/output keys and data volume observer."""
        super().__init__(name)
        self._transforms = transforms
        self._input_key = input_key
        self._output_key = output_key
        self._data_volume_observer: DataVolumeObserver = (
            data_volume_observer or LoggingDataVolumeObserver()
        )

    def execute(self, context: FlowContext) -> None:
        """Reads input_key, awaits the transform chain under one loop, writes output_key."""
        with track_data_volume(
            self._data_volume_observer, self, context, self._input_key, self._output_key
        ):
            result: Iterable[Any] = context.get(self._input_key)
            logger.debug(
                "AsyncApplyStep %r: applying %d async transform(s)",
                self.name,
                len(self._transforms),
            )
            result = asyncio.run(self._apply_chain(result))
            context.put(self._output_key, result)

    async def _apply_chain(self, result: Iterable[Any]) -> Iterable[Any]:
        """Awaits each transform in sequence; transform N+1 starts only after N completes."""
        for transform in self._transforms:
            result = await transform(result)
        return result

    def get_required_keys(self) -> set[str]:
        """Requires input_key in the context."""
        return {self._input_key}

    def get_produced_keys(self) -> set[str]:
        """Produces output_key in the context."""
        return {self._output_key}
```

Then export it from `orchestrators/steps/generic/__init__.py`: add
`from .async_apply_step import AsyncApplyStep` (keep imports alphabetical) and add
`"AsyncApplyStep"` to `__all__` (first entry, keeping the list alphabetical).

**Tests** (intent, not contract — see the write-plan skill's "Note on tests"):
File `tests/guidami_ai_patente_ingestor/orchestrators/steps/generic/test_async_apply_step.py`
(no `__init__.py` in test dirs, per `.claude/rules/code-conventions.md`). Use a real
`FlowContext` and plain `async def` transforms:
- Add: `::test_transforms_run_in_sequence` — two async transforms append markers to a shared list, each `await asyncio.sleep(0)` before/after appending; assert the recorded order proves transform 2 starts only after transform 1 returns (e.g. list == `["t1-start", "t1-end", "t2-start", "t2-end"]`).
- Add: `::test_second_transform_receives_first_output` — transform 1 maps `x → x*10`, transform 2 maps `x → x+1`; assert output is `first*10+1` per element (threading works).
- Add: `::test_writes_output_key_and_requires_input_key` — after `execute`, `context.get(output_key)` holds the result; `get_required_keys() == {input_key}`; `get_produced_keys() == {output_key}`.
- Add: `::test_execute_returns_none_and_owns_its_loop` — `execute` returns `None` and runs from a plain sync test (no active loop), proving it owns its own `asyncio.run`.

### 2. Convert `ImageDescriptionEnricher` to `AsyncUseCase`

In `services/quiz/enrichers/image_description_enricher.py`:

1. Change the import `from commons.use_cases import UseCase` → `from commons.use_cases import AsyncUseCase`.
2. Change the class base: `class ImageDescriptionEnricher(AsyncUseCase[Iterable[EnrichedQuizModel], list[EnrichedQuizModel]]):`.
3. Replace the sync `execute` with the async version below (drops the internal `asyncio.run`,
   adds one INFO milestone with the image count — per Decision 7):

```python
    async def execute(self, request: Iterable[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Enrich each quiz item with a road sign description where an image is present."""
        quizzes = list(request)
        quizzes_by_image = self._group_by_image(quizzes)
        logger.info("Describing %d distinct image(s)", len(quizzes_by_image))
        # The event loop is owned by the caller (AsyncApplyStep); this enricher only awaits.
        descriptions = await self._fetch_descriptions(quizzes_by_image)
        return [self._enrich_quiz(quiz, descriptions) for quiz in quizzes]
```

4. Update the outdated `__init__` comment that mentions `execute` spinning a fresh loop via
   `asyncio.run`: the semaphore is still built per-run inside `_fetch_descriptions`, but the
   loop now belongs to `AsyncApplyStep`. Reword to: *"Store the limit, not the Semaphore: an
   asyncio.Semaphore binds to the loop of its first use; the loop is owned by the caller
   (AsyncApplyStep) and the semaphore is built per-run in `_fetch_descriptions`, keeping the
   enricher reusable across runs/loops."*
5. In `_describe_image`, keep the `(FileNotFoundError, PermissionError)` branch as-is (already
   concise, no traceback). Change the generic branch to concise WARNING + DEBUG traceback
   (per Decision 7):

```python
        except Exception as exc:
            # Per-image degrade is intentional: one bad image must not kill the batch.
            # TODO: narrow this broad catch once the agent domain-exception hierarchy lands.
            logger.warning("Failed to describe image, skipping: %s (%s)", image, exc)
            logger.debug("Image description failed for %s", image, exc_info=True)
            return None
```

`_group_by_image`, `_fetch_descriptions`, `_enrich_quiz` are unchanged (they are already
async where needed).

**Tests** (intent, not contract):
- Modify: `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_image_description_enricher.py` — every test function becomes `async def` and calls `result = await enricher(questions)` (instead of `enricher(questions)`). Assertions unchanged. The fake describer's `run` is already async (AsyncMock via `spec=RoadSignDescriberAgent`), so no fake changes needed. The generic-exception test still asserts a WARNING record is present (message now ends with `(…)`); it must NOT assert on traceback text.

### 3. Convert `NormReferenceEnricher` to `AsyncUseCase` with bounded gather

Rewrite `services/quiz/enrichers/norm_reference_enricher.py`. Keep `_DedupeKey`, `_make_key`,
`_apply_metadata` unchanged. Change the import to `AsyncUseCase`, add `import asyncio`, and
replace the class body's methods as follows:

```python
class NormReferenceEnricher(AsyncUseCase[Iterable[EnrichedQuizModel], list[EnrichedQuizModel]]):
    """Enriches sub-questions with norm metadata generated by the LLM.

    The dedup key is `(topic, text, correct_answer, image_filename)`: exact duplicates get a
    single agent call; the result is propagated to all rows sharing the same key. Unique
    calls run concurrently under `asyncio.gather`, bounded by a semaphore.
    """

    def __init__(self, max_concurrency: int, agent: NormReferenceDescriberAgent) -> None:
        """Injects the concurrency limit and the LLM agent for norm metadata generation."""
        # Store the limit, not the Semaphore: an asyncio.Semaphore binds to the loop of its
        # first use; the loop is owned by the caller (AsyncApplyStep), so the semaphore is
        # built per-run in _build_metadata_map.
        self._max_concurrency = max_concurrency
        self._agent = agent

    async def execute(self, request: Iterable[EnrichedQuizModel]) -> list[EnrichedQuizModel]:
        """Runs norm enrichment on every sub-question.

        Args:
            request: Iterable of enriched sub-questions to enrich.

        Returns:
            List of sub-questions with `quiz_metadata` populated where possible.
        """
        questions = list(request)
        metadata_map = await self._build_metadata_map(questions)
        return [self._apply_metadata(q, metadata_map) for q in questions]

    def _apply_metadata(
        self,
        q: EnrichedQuizModel,
        metadata_map: dict[_DedupeKey, NormReferenceDescriberResponse],
    ) -> EnrichedQuizModel:
        response = metadata_map.get(_make_key(q))
        if response is None:
            return q
        return NormReferenceDescriberMapper.from_response_to_enriched_quiz(q, response)

    async def _build_metadata_map(
        self, questions: list[EnrichedQuizModel]
    ) -> dict[_DedupeKey, NormReferenceDescriberResponse]:
        unique = list(deduplicate(questions, key=_make_key))
        logger.info("Generating norm metadata for %d unique question(s)", len(unique))
        semaphore = asyncio.Semaphore(self._max_concurrency)  # bound to this run's loop
        responses = await asyncio.gather(*(self._call_agent(q, semaphore) for q in unique))
        # gather preserves input order -> lockstep zip, no index bookkeeping.
        return {
            _make_key(q): response
            for q, response in zip(unique, responses, strict=True)
            if response is not None
        }

    async def _call_agent(
        self, q: EnrichedQuizModel, semaphore: asyncio.Semaphore
    ) -> NormReferenceDescriberResponse | None:
        try:
            req = NormReferenceDescriberMapper.from_enriched_quiz_to_request(q)
            async with semaphore:
                return await self._agent.run(req, images=())
        except Exception as exc:
            logger.warning(
                "Failed to generate norm reference metadata, skipping: topic=%r text=%r (%s)",
                q.topic,
                q.text,
                exc,
            )
            logger.debug("Norm reference metadata generation failed", exc_info=True)
            return None
```

Note the degrade path: concise WARNING (no traceback) + DEBUG traceback, per Decision 7.

**Tests** (intent, not contract):
- Modify: `tests/guidami_ai_patente_ingestor/services/quiz/enrichers/test_norm_reference_enricher.py`:
  - `_make_agent_mock()` sets `agent.run.return_value = response` (async via `MagicMock(spec=NormReferenceDescriberAgent)` so `run` is an AsyncMock) instead of `agent.run_sync`.
  - Each test becomes `async def` and calls `await enricher(questions)`.
  - `NormReferenceEnricher(...)` is constructed with a leading `max_concurrency` arg, e.g. `NormReferenceEnricher(8, agent)`.
  - Call-count assertions target `agent.run.call_count` (not `run_sync`).
  - The failure test uses `agent.run.side_effect = RuntimeError(...)`; it still asserts a WARNING record is present and that `quiz_metadata` stays `None`.

### 4. Add `norm_reference_describer_concurrency` config field

In `configs/ingestor_config.py`, next to `road_sign_describer_concurrency: int = 8`, add:

```python
    norm_reference_describer_concurrency: int = 8
```

(`IngestorConfig` is `frozen=True` per `.claude/rules/code-conventions.md` — no change to that.)

**Tests** (intent, not contract):
- Modify (only if such a test exists): any `IngestorConfig` defaults test — add an assertion `config.norm_reference_describer_concurrency == 8`. If no such test exists, none is added.

### 5. Add `MAPPED_QUIZ` context key

In `orchestrators/context_keys.py`, add next to the quiz keys:

```python
MAPPED_QUIZ = "mapped_quiz"  # cleaned→enriched map output; async-enrichment input
```

**Tests** (intent, not contract): none (module-level constant).

### 6. Rewire `build_quiz_enrichment_flow`

In `orchestrators/quiz_flows.py`:

1. Add `from .steps.generic import AsyncApplyStep` (or extend the existing generic-steps
   import) alongside the existing `from flowstep.steps import ApplyStep`.
2. Build the norm enricher with the new config field:
   `NormReferenceEnricher(config.norm_reference_describer_concurrency, norm_describer)`
   (keep `ImageDescriptionEnricher(config.road_sign_describer_concurrency, describer)`).
3. Replace the single `enrich_step = ApplyStep("enrich", ForEach(...), ImageDescriptionEnricher(...), NormReferenceEnricher(...), input_key=CLEANED_QUIZ, output_key=ENRICHED_QUIZ)`
   with two steps:

```python
    map_step = ApplyStep(
        "map_cleaned_quiz",
        ForEach(QuizMapper.from_cleaned_to_enriched),
        input_key=context_keys.CLEANED_QUIZ,
        output_key=context_keys.MAPPED_QUIZ,
    )
    enrich_step = AsyncApplyStep(
        "enrich_quiz",
        ImageDescriptionEnricher(config.road_sign_describer_concurrency, describer),
        NormReferenceEnricher(config.norm_reference_describer_concurrency, norm_describer),
        input_key=context_keys.MAPPED_QUIZ,
        output_key=context_keys.ENRICHED_QUIZ,
    )
```

4. Add both steps to the builder in order: `.add_step(load_step).add_step(map_step).add_step(enrich_step).add_step(write_step)`.
5. Update the function docstring's step mapping to:
   `LoadJsonStep → ApplyStep(map_cleaned_quiz) → AsyncApplyStep(enrich_quiz) → WriteJsonStep`,
   and note that image enrichment completes before norm enrichment (single loop, sequential).

**Tests** (intent, not contract):
- Modify: any quiz-enrichment-flow test that asserts step names/structure — update to the
  two-step (`map_cleaned_quiz` + `enrich_quiz`) shape. If the flow is only exercised via
  `validate=True` structural validation, confirm the new keys chain
  (`CLEANED_QUIZ → MAPPED_QUIZ → ENRICHED_QUIZ`) passes validation.

## Definition of Done

Variable block (plan-specific):

- [ ] `python -c "from guidami_ai_patente_ingestor.orchestrators.steps.generic import AsyncApplyStep"` succeeds
- [ ] `grep -rn "asyncio.run" src/guidami_ai_patente_ingestor/services/quiz/enrichers/` returns nothing (loop ownership moved out of the enrichers)
- [ ] `grep -n "asyncio.run" src/guidami_ai_patente_ingestor/orchestrators/steps/generic/async_apply_step.py` returns exactly one match
- [ ] `grep -rn "run_sync" src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py` returns nothing
- [ ] `grep -n "class ImageDescriptionEnricher(AsyncUseCase" src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py` matches
- [ ] `grep -n "class NormReferenceEnricher(AsyncUseCase" src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py` matches
- [ ] `grep -n "norm_reference_describer_concurrency" src/guidami_ai_patente_ingestor/configs/ingestor_config.py` matches
- [ ] `grep -n "MAPPED_QUIZ" src/guidami_ai_patente_ingestor/orchestrators/context_keys.py` matches
- [ ] Both enrichers are multi-level: `grep -c "logger.debug" src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py` and `.../image_description_enricher.py` each return ≥ 1, and `grep -c "logger.info" .../norm_reference_enricher.py` and `.../image_description_enricher.py` each return ≥ 1
- [ ] No traceback on the WARNING degrade path: `grep -n "exc_info" src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py` shows `exc_info` only on `logger.debug(` lines (never on a `logger.warning(` call)
- [ ] `uv run ingest prepare quiz --force` completes with no `Event loop is closed` / `ModelAPIError` in the logs, and no multi-line Python traceback is printed to stdout for a skipped item (a skipped item shows a single concise WARNING line)

Fixed block (same for every plan):

- [ ] `uv run pytest` green (including new tests)
- [ ] `uv run pyright` clean
- [ ] `uv run ruff check src tests` clean
- [ ] Plan updated to `status: Implemented`
