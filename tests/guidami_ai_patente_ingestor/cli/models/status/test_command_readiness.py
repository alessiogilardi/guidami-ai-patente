from guidami_ai_patente_ingestor.cli.models.status import (
    CommandReadiness,
    ReadinessState,
    SourceReadiness,
)


def test_summary_counts_states() -> None:
    """The summary property aggregates per-source states, including zero counts."""
    readiness = CommandReadiness(
        command="prepare",
        entity="knowledge",
        sources=[
            SourceReadiness(source="cds", state=ReadinessState.SKIP),
            SourceReadiness(source="cap", state=ReadinessState.RUNNABLE),
        ],
    )

    assert readiness.summary == {
        ReadinessState.RUNNABLE: 1,
        ReadinessState.SKIP: 1,
        ReadinessState.BLOCKED: 0,
    }
