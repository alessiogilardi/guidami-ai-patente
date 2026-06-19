from pydantic import BaseModel, ConfigDict


class PipelineLayerConfig(BaseModel):
    """Selettori di layer per una pipeline (input e output)."""

    model_config = ConfigDict(frozen=True)

    input_layer: str
    output_layer: str | None = None
