from enum import StrEnum, auto


class TrackerBackend(StrEnum):
    """Where `build_llm_call_tracker` sends `LlmCallLogEntity` rows.

    Only Postgres exists today; the enum is the extension point for a second sink
    (a file, an OTLP exporter) without changing the config field's type.
    """

    POSTGRES = auto()
