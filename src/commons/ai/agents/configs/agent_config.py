from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    """Configuration for an agent, safely loaded from YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(
        default=None,
        description="Identity used as `LlmCallLog.caller`; defaults to the class name.",
    )

    model_name: str = Field(
        ...,
        description="The ID of the model to use (e.g. openrouter/anthropic/claude-3.5-sonnet).",
    )

    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Model creativity. Typical: 0.0 (deterministic) - 2.0 (creative).",
    )

    max_tokens: int | None = Field(
        default=None, gt=0, description="Maximum token limit for the response."
    )

    timeout: float = Field(default=60.0, gt=0.0, description="Request timeout in seconds.")

    num_retries: int = Field(
        default=3, ge=0, description="Number of retries on network or parsing error."
    )

    system: str = Field(
        ..., min_length=1, description="The system prompt used to instruct the agent."
    )

    user: str = Field(
        ...,
        min_length=1,
        description="User prompt template; supports variables with the $var syntax.",
    )
