from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class LlmCallCaptureModel(BaseModel):
    """Intermediate model: the fields captured by `LlmCallCapture` for one call.

    Bridges `LlmCallCapture` (stateful context manager) and `LlmCallLogMapper`
    (stateless transformation to the persistable `LlmCallLog` entity) — not
    persisted itself.
    """

    caller: str
    model: str
    prompt: str
    system_prompt: str | None
    response: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None = None
    status: Literal["success", "error"]
    error_message: str | None
    latency_ms: int | None
    start_time: datetime | None
    end_time: datetime | None
