from domain.entities.observability import LlmCallLog

from ..models import LlmCallCaptureModel


class LlmCallLogMapper:
    """Stateless transformation from `LlmCallCaptureModel` to the persistable `LlmCallLog`."""

    @staticmethod
    def from_model_to_entity(data: LlmCallCaptureModel) -> LlmCallLog:
        """Maps captured call data to `LlmCallLog`.

        `cost_usd` is always `None`: it is computed later, off the hot path, by
        `QueuedLlmCallTracker`.
        """
        return LlmCallLog(
            caller=data.caller,
            model=data.model,
            prompt=data.prompt,
            system_prompt=data.system_prompt,
            response=data.response,
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            total_tokens=data.total_tokens,
            cost_usd=None,
            status=data.status,
            error_message=data.error_message,
            latency_ms=data.latency_ms,
            start_time=data.start_time,
            end_time=data.end_time,
        )
