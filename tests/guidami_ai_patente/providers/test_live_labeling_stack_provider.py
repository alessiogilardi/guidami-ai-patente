"""The live path's collaborators, assembled once over one pool (AD-16, D3)."""

from pywire import get_default_container

from guidami_ai_patente.clients import PostgresClientProvider
from guidami_ai_patente.providers import LabelingStackProvider, LiveLabelingStackProvider


def test_the_provider_exposes_the_four_live_collaborators(api_client: object) -> None:
    provider = get_default_container().resolve(LiveLabelingStackProvider)

    assert hasattr(provider.corpus, "dense_top_k")
    assert hasattr(provider.quiz, "find_with_vector")
    assert hasattr(provider.golden_set, "find_or_create_live_run")
    assert hasattr(provider.candidate_set, "execute")
    assert hasattr(provider.question_labeling, "execute")


def test_the_stack_reads_through_the_one_pooled_client(api_client: object) -> None:
    """AD-26: one pool per process, or the threaded SQL stages queue behind each other."""
    container = get_default_container()

    provider = container.resolve(LiveLabelingStackProvider)
    expected = container.resolve(PostgresClientProvider).client

    assert provider.corpus._client is expected  # noqa: SLF001 — asserting the wiring
    assert provider.golden_set._client is expected  # noqa: SLF001


def test_the_judge_is_built_from_the_epochs_own_agent_config(api_client: object) -> None:
    """AD-12/AD-22: the judge must load the very prompt whose hash is in the epoch."""
    container = get_default_container()

    identity = container.resolve(LabelingStackProvider)
    provider = container.resolve(LiveLabelingStackProvider)

    assert provider.question_labeling._agent._model_name == identity.agent_config.model_name  # noqa: SLF001


def test_resolving_the_epoch_does_not_build_the_judge(api_client: object) -> None:
    """D3: the FR-14 diagnostic and POST /check must not drag the LLM graph along."""
    identity = get_default_container().resolve(LabelingStackProvider)

    assert not hasattr(identity, "question_labeling")
    assert not hasattr(identity, "judge")
