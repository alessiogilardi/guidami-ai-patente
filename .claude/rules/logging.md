# Logging levels — use them purposefully, never uniformly

A file that logs everything at one level (all `debug`, or all `info`) is not "clear
and useful" — it gives the reader no way to filter signal from trace noise. Each
level has a distinct job; a module that does meaningful work should use more than
one of them, not default to whichever level was convenient at write time.

| Level | Meaning | Example |
|---|---|---|
| `debug` | Fine-grained trace, only useful when actively debugging. Off by default in production. | "Calling agent %r (model=%s)" before dispatch |
| `info` | One line marking a meaningful unit of work completed — operational visibility during a normal run. | "Agent %r call completed", "wrote N items" |
| `warning` | A recoverable/degraded condition: something was skipped, a fallback kicked in, a retry happened. Always pair with `exc_info=True` when there is an active exception. | "Failed to describe image, skipping: %s" |
| `error` | An unrecoverable failure about to propagate or abort a run. Rare: per "fail explicitly, never swallow exceptions" (`~/.claude/rules/python/standards.md`), most exceptions are left to propagate uncaught and get logged once, at the boundary that actually catches them — not speculatively at every layer they pass through. |

## Rules

- **No single-level files.** If a module's logging only ever uses one level across
  multiple call sites, that's a signal the levels weren't chosen deliberately —
  reassess using the table above.
- **Bracket, don't duplicate.** A `debug` before an operation + an `info` after it
  succeeds is enough — don't also log the same fact at `info` right before returning.
- **Never log secrets or full payloads at `info`.** API keys, full prompts/responses,
  and other potentially large or sensitive content belong at `debug` at most, and
  only when they add real trace value (prefer summarizing — length, id, truncated
  preview — over dumping the whole payload even at `debug`).
- **On the exception path, log once, at the point that decides whether to swallow or
  re-raise** — not at every intermediate frame the exception passes through.

## String formatting: lazy `%s`/`%r` args, never f-strings

All logging calls in this project pass lazy `%`-style **arguments** —
`logger.debug("Calling agent %r (model=%s)", name, model)` — never f-strings, and never
pre-formatting (`%`, `.format()`, `+`). This is **enforced by ruff** (`G` ruleset; `G004`
specifically rejects f-strings in logging calls). Passing `%s`-args is not flagged; only
building the string yourself is.

Rationale — lazy args defer string construction until the record is actually emitted, which
matters most in the **inner / hot / parallel** paths: per-item warnings inside
`asyncio.gather`, per-LLM-call traces, anything firing many times per run (especially
`debug`, usually disabled — the formatting cost is skipped entirely). For **outer /
structural** one-shot logs (phase milestones, counts) f-strings would read a little better,
but we deliberately keep `%s` **everywhere** so the convention is a single mechanically
enforced rule rather than a per-log judgement call. Conceptually: the deeper/more frequent
the log, the more `%s` earns its keep; we simply extend it to the outer logs too for
uniformity.

This **overrides** the global `standards.md` "f-strings always (no %)" rule **for logging
only** — f-strings remain the default everywhere else in the codebase.

## Reference implementation

`src/commons/ai/agents/base_agent.py::BaseAgent.run`/`run_sync` — `debug` before
dispatch (agent name + model, useful to reconstruct call ordering when multiple
agents/enrichers interleave in the same pipeline run), `info` after a successful
call (operational visibility). No log on the exception path: `run`/`run_sync` don't
catch, so the exception propagates to whichever call site logs it once (e.g.
`NormReferenceEnricher._call_agent`, `ImageDescriptionEnricher._describe_image`).
