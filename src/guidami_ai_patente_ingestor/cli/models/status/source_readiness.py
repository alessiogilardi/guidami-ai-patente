from pydantic import BaseModel, ConfigDict

from .readiness_state import ReadinessState


class SourceReadiness(BaseModel):
    """Readiness of a single source for a given command."""

    model_config = ConfigDict(frozen=True)

    source: str
    state: ReadinessState
