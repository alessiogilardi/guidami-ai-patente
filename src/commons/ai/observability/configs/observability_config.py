from pydantic_settings import SettingsConfigDict

from commons.configs import BaseConfig

from ..enums import TrackerBackend


class ObservabilityConfig(BaseConfig):
    """LLM call tracking settings.

    Root and self-loading: read from `configs/observability_config.yaml` and
    `LLM_TRACKING_*` environment variables, deliberately not nested inside
    `IngestorConfig` so the module stays removable in one piece and the future
    FastAPI app can load it without an ingestor config.
    """

    model_config = SettingsConfigDict(
        yaml_file="configs/observability_config.yaml",
        env_prefix="LLM_TRACKING_",
    )

    enabled: bool = True
    backend: TrackerBackend = TrackerBackend.POSTGRES
    table: str = "llm_call_logs"
    queue_join_timeout_s: float = 10.0
