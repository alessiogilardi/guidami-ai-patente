import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse
from pydantic_ai.run import AgentRunResult

from ..entities import LlmCallLogEntity
from ..models import TrackedCaller

logger = logging.getLogger(__name__)

# Matches the `NUMERIC(12, 6)` column type of `llm_call_logs.cost_usd`.
_QUANTIZE = Decimal("0.000001")


class PydanticAILlmCallRecorder:
    """Adapts one pydantic_ai call to one `LlmCallLogEntity`.

    Enter the context around the pydantic_ai call and pass the `AgentRunResult` to
    `record` on success. `__exit__` always stamps `latency_ms`/`end_time`, marks
    `status="error"` plus `error_message` when the block raised, emits this call's
    `info` log line, and returns `False` so the failure propagates unchanged.

    `latency_ms` is measured with `time.perf_counter()` (monotonic, immune to
    wall-clock adjustments); `start_time`/`end_time` are separate `datetime.now(UTC)`
    stamps recorded for display only, so the two are not guaranteed to agree.

    Stateful — one stopwatch, one response. A fresh instance per call, never shared
    across calls of the same agent: `asyncio.gather` runs several calls concurrently on
    one `BaseAgent`, and a shared recorder would clobber their timings.
    """

    def __init__(self, tracked_caller: TrackedCaller, prompt: str) -> None:
        """Stores the call's identity and prompt; the stopwatch starts on `__enter__`."""
        self._tracked_caller = tracked_caller
        self._prompt = prompt
        self._response: str | None = None
        self._input_tokens: int | None = None
        self._output_tokens: int | None = None
        self._total_tokens: int | None = None
        self._cost_usd: Decimal | None = None
        self._status: Literal["success", "error"] = "success"
        self._error_message: str | None = None
        self._latency_ms: int | None = None
        self._started_at: float = 0.0
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None

    def __enter__(self) -> "PydanticAILlmCallRecorder":
        """Starts the stopwatch and stamps `start_time`."""
        self._started_at = time.perf_counter()
        self._start_time = datetime.now(UTC)
        return self

    def record(self, result: AgentRunResult[Any]) -> None:
        """Records a successful call's response, token usage, and cost from `result`."""
        usage = result.usage
        self._response = _response_text(result.output)
        self._input_tokens = usage.input_tokens
        self._output_tokens = usage.output_tokens
        self._total_tokens = usage.total_tokens
        self._cost_usd = _call_cost(result)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Stamps latency/`end_time`, error fields on failure, and logs the call.

        Never swallows the error.
        """
        self._end_time = datetime.now(UTC)
        self._latency_ms = int((time.perf_counter() - self._started_at) * 1000)
        if exc_value is not None:
            self._status = "error"
            self._error_message = str(exc_value)
        self._log_completion()
        return False

    @property
    def log(self) -> LlmCallLogEntity:
        """This call's row, built directly — no intermediate model, no mapper."""
        return LlmCallLogEntity(
            caller=self._tracked_caller.caller,
            model=self._tracked_caller.model,
            prompt=self._prompt,
            system_prompt=self._tracked_caller.system_prompt,
            response=self._response,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._total_tokens,
            cost_usd=self._cost_usd,
            status=self._status,
            error_message=self._error_message,
            latency_ms=self._latency_ms,
            start_time=self._start_time,
            end_time=self._end_time,
        )

    def _log_completion(self) -> None:
        """Emits this call's operational line, and a warning when an expected cost is missing.

        Unlike the helper it replaces (`BaseAgent._log_call_completed`, which sat after
        the `with` block), this runs on the failure path too, so a failed call's latency
        is still visible. The cost warning stays limited to successful calls: a call that
        raised has no cost to report in the first place.
        """
        logger.info(
            "Agent %r call completed (status=%s, latency_ms=%s, tokens=%s in / %s out / "
            "%s total, cost_usd=%s)",
            self._tracked_caller.caller,
            self._status,
            self._latency_ms,
            self._input_tokens,
            self._output_tokens,
            self._total_tokens,
            self._cost_usd,
        )
        missing_expected_cost = self._cost_usd is None and self._tracked_caller.expects_cost
        if self._status == "success" and missing_expected_cost:
            logger.warning(
                "Agent %r call succeeded but the provider reported no cost (model=%s)",
                self._tracked_caller.caller,
                self._tracked_caller.model,
            )


def _response_text(output: object) -> str:
    """Serializes an agent's `output`: JSON for `BaseModel`s, `str()` otherwise."""
    if isinstance(output, BaseModel):
        return output.model_dump_json()

    return str(output)


def _call_cost(result: AgentRunResult[Any]) -> Decimal | None:
    """Sums the provider's reported cost across every `ModelResponse` in this run.

    Mirrors how `result.usage` aggregates tokens across validation retries: a retried
    call incurs real cost per underlying HTTP request, so every
    `ModelResponse.provider_details["cost"]` in `result.new_messages()` is summed, not
    just the last one. Returns `None` when no response reports a cost.
    """
    responses = (
        message for message in result.new_messages() if isinstance(message, ModelResponse)
    )
    costs = [
        Decimal(str(response.provider_details["cost"]))
        for response in responses
        if response.provider_details is not None and "cost" in response.provider_details
    ]
    if not costs:
        return None

    return sum(costs, Decimal(0)).quantize(_QUANTIZE)
