from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class LlmCallLogEntity(BaseModel):
    """Row of the `llm_call_logs` table (see db/init.sql).

    `id` and `created_at` are DB-managed (`BIGSERIAL PRIMARY KEY` and
    `DEFAULT now()`) and have no corresponding field here.
    """

    caller: str
    model: str
    prompt: str
    system_prompt: str | None = None
    response: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: Decimal | None = None
    status: Literal["success", "error"] = "success"
    error_message: str | None = None
    latency_ms: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
