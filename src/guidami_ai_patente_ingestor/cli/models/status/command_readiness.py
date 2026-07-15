from pydantic import BaseModel, ConfigDict

from .readiness_state import ReadinessState
from .source_readiness import SourceReadiness


class CommandReadiness(BaseModel):
    """Aggregate readiness of one command over one entity's sources."""

    model_config = ConfigDict(frozen=True)

    command: str
    entity: str
    sources: list[SourceReadiness]

    @property
    def summary(self) -> dict[ReadinessState, int]:
        """Per-state count across sources, including states with zero occurrences."""
        counts = dict.fromkeys(ReadinessState, 0)
        for source in self.sources:
            counts[source.state] += 1
        return counts
