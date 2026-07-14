from commons.ai.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.road_sign_describer import (
    RoadSignDescriberRequest,
    RoadSignDescriberResponse,
)


class RoadSignDescriberAgent(BaseAgent[RoadSignDescriberRequest, RoadSignDescriberResponse]):
    """Pure LLM wrapper for describing road signs via vision."""

    output_type = RoadSignDescriberResponse
