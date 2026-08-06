"""Root logging configuration: console output plus a per-run `RunArtifactWriter`."""

import argparse
import logging
import os
from pathlib import Path

from commons.observability import LOG_FORMAT, RunArtifactWriter, RunManifest

from .models.run_artifacts import EvaluateManifest, IndexManifest, PrepareManifest, ResetManifest

_MUTED_LOGGER_PREFIXES = ("httpx", "httpcore", "litellm", "openai", "urllib3")


class MutedThirdPartyFilter(logging.Filter):
    """Drops records from noisy third-party loggers, on whichever handler it's attached to.

    A `logging.Filter` on a specific handler, not a `Logger.setLevel()` change: muting
    must only affect what an *interactive* sink displays (this console handler,
    `LogPanelHandler`'s panel) — the run log file's `FileHandler` never gets this filter
    attached, so it always keeps full fidelity (PD-4 in `LogPanelHandler`; the same
    invariant applies here for consistency).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Returns False (drop) for muted-prefix loggers, True (keep) for everything else."""
        return not record.name.lower().startswith(_MUTED_LOGGER_PREFIXES)


def configure_logging(
    project_root: Path,
    args: argparse.Namespace,
    dry_run: bool,
    use_console_handler: bool = True,
) -> RunArtifactWriter | None:
    """Configures the root logger with a console handler; builds a `RunArtifactWriter`.

    Skips the `RunArtifactWriter` when `dry_run` is `True` (no filesystem write of
    any kind — FR-2);
    otherwise builds and returns a not-yet-`__enter__`ed `RunArtifactWriter` wrapping
    the command-appropriate manifest (`_build_manifest`) — the caller (`cli/main.py`)
    enters it via its own `ExitStack` (AD-4) and is responsible for attaching the file
    handler this function used to attach directly.
    """
    # litellm attaches its own StreamHandler to the "LiteLLM" logger the first time it's
    # imported (lazily, inside LiteLLMEmbeddingClient._embed), independent of the root
    # logger this function configures below — that handler defaults to DEBUG when
    # LITELLM_LOG is unset, so it writes straight to stderr, unformatted, bypassing both
    # LOG_FORMAT and MutedThirdPartyFilter below. Must be set before that first import;
    # setdefault so an operator-provided LITELLM_LOG (e.g. for debugging) still wins. This
    # only quiets litellm's *own* handler — its records still propagate to the root logger
    # at INFO (litellm never calls .setLevel() on the "LiteLLM" logger itself), so they
    # still reach our own handlers, filtered by MutedThirdPartyFilter same as httpx/openai.
    os.environ.setdefault("LITELLM_LOG", "WARNING")

    handlers: list[logging.Handler] = []
    if use_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.addFilter(MutedThirdPartyFilter())
        handlers.append(console_handler)

    # force=True: without it, basicConfig is a no-op whenever the root logger already
    # has a handler (e.g. pytest's own log-capture handler during the test session, or
    # a second invocation within the same process), silently skipping ours.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers, force=True)

    if dry_run:
        return None
    return RunArtifactWriter(
        logs_root=project_root / "logs",
        run_id_prefix=f"ingest_{args.command}",
        manifest=_build_manifest(args),
    )


def _build_manifest(args: argparse.Namespace) -> RunManifest:
    """Builds the command-appropriate manifest from `args` (PD-7). Never called for `status`."""
    match args.command:
        case "prepare":
            return PrepareManifest(
                entity=args.entity, source=getattr(args, "source", None), force=args.force
            )
        case "index":
            return IndexManifest(entity=args.entity, source=getattr(args, "source", None))
        case "reset":
            return ResetManifest(entity=args.entity)
        case "evaluate":
            return EvaluateManifest(entity=args.entity)
        case _:
            raise AssertionError(f"no manifest builder for command {args.command!r}")
