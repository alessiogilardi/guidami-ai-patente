import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from pydantic_ai.messages import ModelResponse
from pydantic_ai.run import AgentRunResult

from ..entities import LlmCallLogEntity
from ..mappers import LlmCallLogMapper
from ..models import LlmCallCaptureModel

# Matches the `NUMERIC(12, 6)` column type of `llm_call_logs.cost_usd`.
_QUANTIZE = Decimal("0.000001")


class _LegacyLlmCallTracker(Protocol):
    """Shape `tracked()` still calls: superseded by the `LlmCallTracker` port (Task 6).

    Kept local (rather than importing the current `LlmCallTracker`) because that port
    was flipped to a context-manager shape this class never adopted — this class is
    unused by `BaseAgent` and slated for removal in Task 8.
    """

    def track(self, log: LlmCallLogEntity) -> None: ...


class PydanticAILlmCallCapture:
    """Pure in-memory context manager measuring a single `BaseAgent` call.

    Enter the context around the pydantic_ai call; call `record` with the
    `AgentRunResult` on success. `__exit__` always stamps `latency_ms` and,
    on exception, `status="error"` plus `error_message` — then returns
    `False` so the failure always propagates unchanged (see
    `docs/plans/2026-07-13--llm-call-tracking.md`, Decision 2). `cost_usd` is
    read from OpenRouter's own reported cost (`ModelResponse.provider_details
    ["cost"]`, see `docs/plans/2026-07-16--openrouter-native-cost-tracking.md`)
    and stays `None` when no response in the run reports one.

    `latency_ms` is measured with `time.perf_counter()` (monotonic, immune to
    wall-clock adjustments); `start_time`/`end_time` are separate wall-clock
    timestamps (`datetime.now(UTC)`), recorded only for observability/display.

    The instance itself has no knowledge of `LlmCallTracker` — use the
    `tracked` classmethod to compose a capture with a tracker in one context
    manager; call sites that only need the raw measurement (e.g. tests) can
    still use the class directly.
    """

    def __init__(
        self,
        caller: str,
        model: str,
        prompt: str,
        system_prompt: str | None,
    ) -> None:
        """Stores the call's identifying fields; the stopwatch starts on `__enter__`."""
        self._caller = caller
        self._model = model
        self._prompt = prompt
        self._system_prompt = system_prompt
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

    @classmethod
    @contextmanager
    def tracked(
        cls,
        caller: str,
        model: str,
        prompt: str,
        system_prompt: str | None,
        tracker: _LegacyLlmCallTracker,
    ) -> Iterator["PydanticAILlmCallCapture"]:
        """Builds a capture for one call and tracks its `log` via `tracker` on exit.

        Composes the pure per-call measurement with persistence: `tracker.track`
        runs in `finally`, so error calls are logged too, mirroring `__exit__`'s
        own contract of never swallowing the underlying exception. A fresh
        capture per call — never share one instance across calls (e.g. by
        building it once in `BaseAgent.__init__`): it is stateful (one
        stopwatch, one response), so concurrent calls would clobber each
        other's timings/tokens.
        """
        capture = cls(caller=caller, model=model, prompt=prompt, system_prompt=system_prompt)
        try:
            with capture:
                yield capture
        finally:
            tracker.track(capture.log)

    def __enter__(self) -> "PydanticAILlmCallCapture":
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
        """Stamps latency/`end_time` and, on exception, error status/message.

        Never swallows the error.
        """
        self._end_time = datetime.now(UTC)
        self._latency_ms = int((time.perf_counter() - self._started_at) * 1000)
        if exc_value is not None:
            self._status = "error"
            self._error_message = str(exc_value)
        return False

    @property
    def log(self) -> LlmCallLogEntity:
        """Builds the `LlmCallLogEntity` for this call via `LlmCallLogMapper`."""
        return LlmCallLogMapper.from_model_to_entity(self._to_capture_data())

    def _to_capture_data(self) -> LlmCallCaptureModel:
        """Projects this call's captured fields onto `LlmCallCaptureModel`."""
        return LlmCallCaptureModel(
            caller=self._caller,
            model=self._model,
            prompt=self._prompt,
            system_prompt=self._system_prompt,
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


def _response_text(output: object) -> str:
    """Serializes an agent's `output` for persistence: JSON for `BaseModel`s, `str()` otherwise."""
    if isinstance(output, BaseModel):
        return output.model_dump_json()

    return str(output)


def _call_cost(result: AgentRunResult[Any]) -> Decimal | None:
    """Sums OpenRouter's reported cost across every `ModelResponse` in this run.

    Mirrors how `result.usage` aggregates `input_tokens`/`output_tokens` across
    validation retries: a retried call incurs real cost for each underlying HTTP
    request, so every `ModelResponse.provider_details["cost"]` in
    `result.new_messages()` is summed, not just the last one. Returns `None`
    when no response reports a cost.
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
