"""Container-managed provider for the shared labeling configuration epoch."""

from pywire import Autowired, provider

from commons.ai.agents import AgentConfig
from guidami_ai_patente.repositories import AgentConfigRepository
from labeling.configs import LabelingConfig
from labeling.mappers import LabelingEpochMapper
from labeling.models import LabelingEpoch


@provider
class LabelingStackProvider:
    """Loads the judge's prompt once and exposes the epoch it implies.

    The epoch is the six-field key `labeling_runs` is unique on for live runs and the
    FR-8 precedence query filters by: `judge_model` and `prompt_version` derived from
    the agent YAML found under `agents_dir`, plus `candidate_variant`, `dense_k`,
    `text_k` and `lexeme_fields` from the shared `LabelingConfig` (AD-8, AD-27).
    Resolving it here, once, means every request compares against the same value and
    the FR-14 startup check reports on the same judge the reads filter by.

    Loading the prompt is I/O, and doing it in `__init__` makes a missing or
    unreadable `comma_labeler.yaml` a startup failure rather than a per-request one —
    the same fail-fast intent as `agents_dir` having no default (AD-22).

    The prompt is loaded through `AgentConfigRepository`, the same door
    `ExplanationWriterAgent` uses in plan 3. `labeling.wiring.build_comma_labeler_config`
    is deliberately not called: it is a scoped YAML load and nothing more, so using it
    would only add a second way to read the same file. What AD-12 actually requires to be
    single-implementation is the *derivation* — `prompt_version(system, user)` and
    `LabelingEpochMapper` — and that is exactly what this class delegates to.

    This plan needs no model client: the quiz endpoints call nothing. Plan 3 adds the
    `OpenRouterProvider` and the agents built on it.
    """

    labeling_config: Autowired[LabelingConfig]
    agent_configs: Autowired[AgentConfigRepository]

    def __init__(self) -> None:
        """Loads `comma_labeler.yaml` and derives the configuration epoch from it."""
        self.agent_config: AgentConfig = self.agent_configs.load("comma_labeler")
        self.epoch: LabelingEpoch = LabelingEpochMapper.from_config_to_epoch(
            self.labeling_config, self.agent_config
        )
