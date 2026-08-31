from typing import Protocol

from ..entities import LlmCallLogEntity


class LlmCallLogRepository(Protocol):
    """Port for the sink that stores call logs.

    Public and cross-package, unlike the private duplicate it replaces: the tracker
    depends on this rather than on a concrete Postgres repository, so a second backend
    (a file, an OTLP exporter) only has to satisfy `insert`.
    """

    def insert(self, log: LlmCallLogEntity) -> None:
        """Stores one `LlmCallLogEntity`."""
        ...
