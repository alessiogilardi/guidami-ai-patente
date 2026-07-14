from commons.ai.agents import BaseAgent
from guidami_ai_patente_ingestor.agents.dto.norm_reference_describer import (
    NormReferenceDescriberRequest,
    NormReferenceDescriberResponse,
)


class NormReferenceDescriberAgent(
    BaseAgent[NormReferenceDescriberRequest, NormReferenceDescriberResponse]
):
    """Pure LLM wrapper for generating normative metadata from quiz questions."""

    output_type = NormReferenceDescriberResponse
