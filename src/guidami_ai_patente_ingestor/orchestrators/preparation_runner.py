"""Generic per-source runner: encapsulates the idempotent skip of a preparation flow."""

import logging
from pathlib import Path

from flowstep import Flow

logger = logging.getLogger(__name__)


def run_preparation(flow: Flow, out_path: Path, force: bool) -> None:
    """Runs `flow` unless `out_path` already exists and `force` is False.

    Single-source helper: no internal loop over sources, no injection of
    `source` into the context (it is already injected into the steps at the
    factory). If a loop over multiple sources is needed, the caller does it.

    Args:
        flow: Preparation flow already assembled for the current source.
        out_path: Path of the flow's output artifact (resolved by the caller).
        force: If True, runs the flow even if `out_path` already exists.
    """
    if out_path.exists() and not force:
        logger.info(f"{out_path} already exists, skipping")
        return
    flow.run()
