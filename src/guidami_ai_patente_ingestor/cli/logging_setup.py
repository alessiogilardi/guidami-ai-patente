"""Root logging configuration: console output plus a per-run log file under `logs/`."""

import logging
import os
from pathlib import Path

from commons.observability import LOG_FORMAT, RunArtifactWriter

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
    project_root: Path, command: str, dry_run: bool, use_console_handler: bool = True
) -> Path | None:
    """Configures the root logger with a console handler, plus a file handler unless `dry_run`.

    `--dry-run` commands are advertised as making no filesystem writes (see
    `render_dry_run`); logging to `logs/` would break that contract, so dry runs log to
    console only.

    The caller passes `use_console_handler=False` when a `LiveDashboard` owns the
    console instead (its own `LogPanelHandler` is attached/detached by the dashboard's
    `__enter__`/`__exit__`, not here): in that case the run log file is the only sink
    this function installs.

    Returns the log file path, or None when `dry_run` is True.
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
    log_file: Path | None = None
    if not dry_run:
        run_dir = RunArtifactWriter.build_run_dir(project_root / "logs", f"ingest_{command}")
        log_file = run_dir / "run.log"
        handlers.append(logging.FileHandler(log_file))

    # force=True: without it, basicConfig is a no-op whenever the root logger already
    # has a handler (e.g. pytest's own log-capture handler during the test session, or
    # a second invocation within the same process), silently skipping ours.
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=handlers, force=True)
    return log_file
