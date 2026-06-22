from pydantic import BaseModel, ConfigDict, Field


class PipelineLayerConfig(BaseModel):
    """Selettori di layer e source per una pipeline."""

    model_config = ConfigDict(frozen=True)

    input_layer: str
    output_layer: str | None = None
    sources: list[str] = Field(default_factory=list)
