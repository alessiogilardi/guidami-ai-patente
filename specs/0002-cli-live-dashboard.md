# Spec 0002: Live dashboard for the ingest CLI

| | |
|---|---|
| **Id** | 0002 |
| **Status** | draft |
| **Date** | 2026-07-31 |
| **Discussion log** | none — compiled directly from conversation |
| **Supersedes / superseded by** | — |

## Problem & Motivation

`ingest prepare` and `ingest index` are long-running batch commands: a single
`prepare knowledge --source cds` run issues one LLM call per article, bounded only by a
concurrency semaphore, and can occupy the terminal for tens of minutes. During that time
the operator's only feedback is an undifferentiated stream of log lines scrolling past —
the same stream that carries step milestones, per-item warnings, and library noise, with
no visual separation and no indication of how much work remains.

Two distinct problems follow. First, the log output has no dedicated region: it competes
with everything else the command prints, and there is no way to see "what is happening
right now" without scrolling back through history. Second, there is no notion of
progress at all — an operator cannot distinguish a run that is 10% through its articles
from one that has silently stalled on a hanging HTTP call, and cannot estimate whether
to wait or abort.

Compounding this, the pipeline framework in use exposes lifecycle events only at step
granularity, and the steps are wildly unequal in duration: in `knowledge_enrichment`, one
step (`enrich_articles`) accounts for essentially the entire wall-clock time while its
four siblings complete in milliseconds. Any progress indication derived solely from step
counts would sit motionless at the same percentage for the whole run — technically
accurate, operationally useless.

## Functional Requirements

### FR-1: Log output renders in a dedicated bordered region

While a monitored command runs on an interactive terminal, log records appear inside a
visually delimited panel rather than interleaved with the rest of the command's output.

**Acceptance criteria:**
- Given `ingest prepare knowledge --source cds` running on a TTY, when a log record is
  emitted at the configured level or above, then it appears inside the bordered log
  panel and not in the surrounding terminal scrollback.
- Given the log panel is bounded to N records, when more than N records have been
  emitted, then the panel displays the most recent N and older records are no longer
  displayed.
- Given any monitored run, when the run completes, then the per-run log file under
  `logs/ingest_<command>_<timestamp>/run.log` contains every record emitted, including
  those no longer visible in the panel.

### FR-2: An outer progress bar tracks step position within the flow

While a monitored command runs, a progress bar reflects which step of the flow is
executing and how many steps the flow contains.

**Acceptance criteria:**
- Given a flow of T steps, when step number I starts, then the outer bar displays
  position I of T and is labelled with that step's name.
- Given a flow, when its final step completes successfully, then the outer bar displays
  T of T.

### FR-3: An inner progress bar tracks item completion within instrumented steps

While an instrumented long-running step executes, a second progress bar advances as
individual work items complete, so progress is observable during a single step.

**Acceptance criteria:**
- Given `enrich_articles` processing K articles, when an article's enrichment completes
  (successfully or by the skip/failure path that returns it unchanged), then the inner
  bar advances by exactly one and never exceeds K.
- Given an embedding step processing B batches, when a batch completes, then the inner
  bar advances by exactly one and never exceeds B.
- Given the quiz enrichment step, when items are deduplicated before dispatch, then the
  inner bar's total equals the number of unique items actually sent to the LLM, not the
  number of input quiz items.
- Given an instrumented step, when the step ends, then its inner bar is removed and the
  outer bar advances.

### FR-4: Non-interactive output degrades to plain logging

When output is not an interactive terminal, or plain output is explicitly requested, the
command produces plain log lines with no cursor control or redraw.

**Acceptance criteria:**
- Given stdout is redirected to a file or pipe, when a monitored command runs, then its
  output contains no ANSI cursor-control or redraw sequences and every log record appears
  exactly once, in order.
- Given the `--plain` flag on a TTY, when a monitored command runs, then no dashboard is
  rendered and output matches the non-interactive form.

### FR-5: Failures surface intact

A failing run reports its error with the same fidelity as before the dashboard existed.

**Acceptance criteria:**
- Given a step raises, when the exception propagates out of the flow, then the dashboard
  is torn down before the traceback is written, and the full traceback appears in the
  terminal.
- Given a step raises, when the command exits, then its exit code is non-zero.

### FR-6: Dry-run behaviour is unchanged

`--dry-run` continues to print its step chain and make no filesystem writes.

**Acceptance criteria:**
- Given `--dry-run` on any monitored command, when it runs, then no dashboard is
  rendered, no `logs/` directory is created, and the output matches the current dry-run
  rendering.

## Non-Goals

- `ingest reset` and `ingest status` — neither executes a `Flow`. `reset` issues a
  TRUNCATE that returns immediately, and `status` is already a self-contained rich
  renderer; wrapping either adds surface with nothing to display.
- Instrumenting every step. Only steps whose duration is dominated by per-item work are
  instrumented; cheap map/filter steps are covered by the outer bar alone.
- Scrollback, mouse interaction, or level filtering inside the log panel — the panel is a
  fixed window on recent records, and the run log file remains the complete archive.
- Changing the log file format, location, or the `--dry-run` no-writes contract.
- Modifying the `flowstep` dependency.

## Architectural Decisions

### AD-1: A single `Live` renders both the progress bars and the log panel

One `rich.Live` owns a `Layout` split into a progress region and a bordered log region.
- **Rationale:** Two independent renderers writing to the same terminal corrupt each
  other's output. Composition through a single `Live` is the only arrangement in which
  both requirements can hold simultaneously.
- **Rejected alternatives:** `RichHandler` with a bottom-anchored bar — logs keep the
  full scrollback, so there is no dedicated region (fails FR-1). A full TUI on Textual —
  Textual expects to own the event loop while the async step calls `asyncio.run()` itself,
  and the dependency is disproportionate for a batch CLI.

### AD-2: Progress bars use `rich.progress`, not `tqdm`

- **Rationale:** `rich` is already a project dependency, and `rich.progress.Progress` is a
  renderable that composes inside the `Layout` required by AD-1.
- **Rejected alternatives:** `tqdm` — writes directly to a stream and is not a renderable,
  so it cannot be placed inside the log-panel layout; it would conflict with `Live`
  exactly as the current `StreamHandler` does.

### AD-3: Item-level progress travels through a `ProgressReporter` port with a null default

A `Protocol` port plus a no-op implementation, injected as the last constructor argument
of the instrumented services.
- **Rationale:** Mirrors the port/null-object pair already established in this codebase
  for LLM call tracking, so the pattern is not new. The null default keeps services on a
  single code path with no conditional branching, and leaves existing service tests
  unchanged.
- **Rejected alternatives:** Deriving progress by parsing the log records the panel
  already captures — couples the UI to log message wording, which is fragile and
  contradicts the project's logging conventions. Extending `flowstep` with an item-level
  observer — the instrumented services are not `Step`s, so they would take a framework
  dependency for a presentation concern.

### AD-4: The reporter enters the flows through one parameter on the flow factories

Each `build_*_flow` factory accepts `progress: ProgressReporter | None = None` and uses it
both to register the outer-bar observer on the `FlowBuilder` and to inject into the
services it constructs.
- **Rationale:** `Flow` exposes no way to attach an observer post-construction, so
  something must reach the factories regardless. A single parameter serving both the
  step-level and item-level paths keeps one concept instead of two, and leaves the
  `flowstep` dependency untouched.
- **Rejected alternatives:** Adding `Flow.add_observer()` to `flowstep` — covers only the
  outer bar, so the factory parameter is still needed for the services; the result is two
  mechanisms plus a cross-repo release and version bump.

### AD-5: The port is defined in `commons/`, outside the CLI package

`ProgressReporter` lives in a new `src/commons/observability/` package.
- **Rationale:** The project's CLI-structure rule places a component in `cli/` only when
  nothing outside the CLI uses it. This port is consumed by `commons/` services and
  `orchestrators/` factories, so it belongs in the shared layer. It is separate from the
  existing `commons/ai/observability/` because it is not AI-specific. Its concrete rich
  implementation, being CLI-only, does stay under `cli/rendering/`.
- **Rejected alternatives:** Defining the port inside `cli/` — would force `commons/` and
  `orchestrators/` to import from the CLI package, inverting the dependency direction.

### AD-6: Reporter callbacks mutate state only; rendering stays on the refresh thread

`emit()` and `advance()` append to a bounded deque and increment a counter; no call site
touches the terminal.
- **Rationale:** Records reach the handler from more than one thread — the LLM call
  tracker runs a background worker — while `rich.Live` redraws on its own thread, and item
  ticks originate inside `asyncio.gather` under the async step's own event loop. Confining
  all rendering to the refresh thread is what makes those three contexts safe to mix.
- **Rejected alternatives:** Redrawing synchronously on each callback — serialises the
  hot per-item path against terminal I/O and races the `Live` refresh thread.

## Constraints

- No new runtime dependency: `rich>=13` is already declared and is sufficient.
- The per-run log file remains the complete record; the panel is a bounded view of it.
- `--dry-run` must continue to open no `Live`, write no `logs/` directory, and touch no
  filesystem path.
- Logging calls keep lazy `%s`/`%r` argument style, enforced by ruff's `G` ruleset.
- Injected collaborators go last in constructor signatures, per the project's
  dependency-injection rule.
- All new docstrings, comments and log messages in English.

## Feasibility Evidence

- **AD-1** — supported by: `src/guidami_ai_patente_ingestor/cli/logging_setup.py:38` — the console handler is a plain `logging.StreamHandler` writing to the same stream a `Live` would redraw; constructed in one place, so substituting it is a localised change (verified 2026-07-31 @ 18a58e0)
- **AD-2** — supported by: `pyproject.toml:23` — `rich>=13` is already a declared runtime dependency, so no new package is required (verified 2026-07-31 @ 18a58e0)
- **AD-2** — supported by: `src/guidami_ai_patente_ingestor/cli/rendering/dry_run_renderer.py:14` — the CLI already composes rich renderables (`Panel`) through a `Console`, establishing the idiom (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/commons/ai/observability/protocols/llm_call_tracker.py:6` — an existing `Protocol` port injected as an optional collaborator, the pattern this decision mirrors (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/commons/ai/observability/services/null_llm_call_tracker.py:4` — the matching no-op implementation that lets call sites avoid branching on absence (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/services/knowledge/enrichers/context_enricher.py:50` — `articles = list(request)` materialises the collection before dispatch, so the item total required by FR-3 is known at that point (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/commons/ai/embedding/services/embedding_service.py:27` — `total_batches` is already computed, and line 38 already logs per-batch position, so batch-level ticks require no new counting (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/services/quiz/enrichers/norm_reference_enricher.py:65` — `unique = list(deduplicate(...))` is the post-dedup collection actually dispatched, confirming the FR-3 total must be taken after deduplication (verified 2026-07-31 @ 18a58e0)
- **AD-3** — supported by: `src/guidami_ai_patente_ingestor/services/quiz/enrichers/image_description_enricher.py:69` — `images = list(requests)` is the deduplicated image set dispatched concurrently, the second post-dedup total (verified 2026-07-31 @ 18a58e0)
- **AD-4** — supported by: `.venv/Lib/site-packages/flowstep/core/flow/flow.py:73` — the built `Flow` exposes only `run` and `get_steps`; there is no post-construction observer hook, so injection must happen at build time (verified 2026-07-31 @ 18a58e0)
- **AD-4** — supported by: `src/guidami_ai_patente_ingestor/orchestrators/knowledge_flows.py:135` — the factory constructs the `FlowBuilder` internally and returns a sealed `Flow`, so the observer can only be registered inside the factory (verified 2026-07-31 @ 18a58e0)
- **AD-5** — supported by: `.claude/rules/cli-structure.md:27` — the project rule states a component shared beyond the CLI belongs in the shared layer, which is the test this decision applies (verified 2026-07-31 @ 18a58e0)
- **AD-6** — supported by: `src/guidami_ai_patente_ingestor/services/knowledge/enrichers/context_enricher.py:52` — per-item work runs under `asyncio.gather`, so ticks originate inside a coroutine owned by the async step rather than on the rendering thread (verified 2026-07-31 @ 18a58e0)
- **AD-6** — supported by: `.venv/Lib/site-packages/flowstep/steps/async_apply_step.py:53` — `AsyncApplyStep.apply` calls `asyncio.run`, confirming the step owns its own event loop that the dashboard must not assume control of (verified 2026-07-31 @ 18a58e0)

## Open Questions

- [ ] **non-blocking** — How many records the log panel retains, and whether that bound is
  fixed or configurable — owner: investigation
- [ ] **non-blocking** — Whether the inner bar for embedding counts batches or individual
  items; batches are free today, items would need a finer callback — owner: user
- [ ] **non-blocking** — Whether the panel shows every record at the root level or filters
  noisy third-party loggers (httpx, litellm) — owner: investigation

## Sign-off

- **Scope approved by user:** pending
- **Feasibility asserted:** by write-spec on 2026-07-31, based on Feasibility Evidence above
