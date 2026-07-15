from enum import StrEnum


class ReadinessState(StrEnum):
    """Executability state of a (command, source) pair, computed by `StatusInspector`."""

    RUNNABLE = "runnable"
    SKIP = "skip"
    BLOCKED = "blocked"
