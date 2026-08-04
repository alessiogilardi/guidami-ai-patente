import logging
from collections import deque

from ...logging_setup import MutedThirdPartyFilter

_PANEL_MAX_RECORDS = 15


class LogPanelHandler(logging.Handler):
    """Bounded, filtered log sink feeding the live dashboard's log panel.

    Retains only the most recent `max_records` formatted records, and drops records
    from muted third-party loggers (PD-4, via the shared `MutedThirdPartyFilter`) — both
    filters apply to the panel only; the run log file, attached separately with no such
    filter, still receives every record. Performs no terminal I/O (AD-6): `emit` only
    mutates the internal deque, `snapshot` is the sole read surface, consumed by
    `LiveDashboard`'s renderer on its own refresh thread.
    """

    def __init__(self, max_records: int = _PANEL_MAX_RECORDS) -> None:
        """Sets its own formatter.

        Attached directly to the root logger (PD-5), never passed to
        `logging.basicConfig`, so it would otherwise inherit no format.
        """
        super().__init__()
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        self._mute_filter = MutedThirdPartyFilter()
        self._records: deque[str] = deque(maxlen=max_records)

    def emit(self, record: logging.LogRecord) -> None:
        """Appends the formatted record, unless it comes from a muted logger."""
        if self._mute_filter.filter(record):
            self._records.append(self.format(record))

    def snapshot(self) -> list[str]:
        """Returns a copy of the currently retained records, oldest first."""
        return list(self._records)
