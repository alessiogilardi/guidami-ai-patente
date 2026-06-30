"""Runner generico per-source: incapsula lo skip idempotente di un flow di preparation."""

import logging
from pathlib import Path

from flowstep import Flow

logger = logging.getLogger(__name__)


def run_preparation(flow: Flow, out_path: Path, force: bool) -> None:
    """Esegue `flow` a meno che `out_path` esista già e `force` sia False.

    Helper a singola source: nessun loop interno sulle source, nessuna
    iniezione di `source` nel context (è già iniettata negli step alla factory).
    Il loop su più source, se serve, lo fa il chiamante.

    Args:
        flow: Flow di preparation già assemblato per la source corrente.
        out_path: Path dell'artefatto di output del flow (risolto dal chiamante).
        force: Se True, esegue il flow anche se `out_path` esiste già.
    """
    if out_path.exists() and not force:
        logger.info(f"{out_path} already exists, skipping")
        return
    flow.run()
