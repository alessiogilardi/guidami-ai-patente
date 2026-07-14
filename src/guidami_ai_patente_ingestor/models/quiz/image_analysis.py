from pydantic import BaseModel, ConfigDict


class ImageAnalysis(BaseModel):
    """Full structured output of the road-sign vision LLM, persisted for debugging.

    Mirrors `RoadSignDescriberResponse` (visual_analysis + name + description) and is
    stored inline on `EnrichedQuizModel.image_analysis`. Not part of the embedding or
    DB path.
    """

    model_config = ConfigDict(frozen=True)

    visual_analysis: str
    name: str
    description: str
