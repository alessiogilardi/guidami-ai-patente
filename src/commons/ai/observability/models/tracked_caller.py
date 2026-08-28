from pydantic import BaseModel, ConfigDict


class TrackedCaller(BaseModel):
    """Everything the tracker needs that is fixed for one agent's lifetime.

    Only the prompt varies per call, so `BaseAgent` builds this once in `__init__` and
    passes it by reference on every call. Frozen because a single instance is shared
    across concurrent calls of the same agent (`asyncio.gather` over one `BaseAgent`),
    where an accidental mutation would corrupt sibling calls' rows.
    """

    model_config = ConfigDict(frozen=True)

    caller: str
    model: str
    system_prompt: str | None
    expects_cost: bool
    """Whether this agent's provider is expected to report a per-call cost.

    Only OpenRouter does; for any other OpenAI-compatible provider (e.g. Ollama) a
    missing `cost_usd` is normal and must not produce a warning.
    """
