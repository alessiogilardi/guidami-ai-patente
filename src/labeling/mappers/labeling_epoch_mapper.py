from commons.ai.agents import AgentConfig
from labeling.configs import LabelingConfig
from labeling.models import LabelingEpoch
from labeling.utils import prompt_version


class LabelingEpochMapper:
    """Builds the epoch key from the configuration and the loaded agent prompt.

    The single place `lexeme_fields` is canonicalised (spec 0012, AD-8): both the
    batch pass and the live API path route through here, so the *set* of fields
    changes retrieval while their order never can.
    """

    @staticmethod
    def from_config_to_epoch(config: LabelingConfig, agent_config: AgentConfig) -> LabelingEpoch:
        """Maps `(LabelingConfig, AgentConfig)` to the six-input epoch key.

        Args:
            config: The shared labeling configuration, resolved from
                `configs/labeling.yaml` plus `AGENTS_DIR`.
            agent_config: The already-loaded `comma_labeler.yaml`, which supplies both
                `judge_model` and — through the hash of its prompt text —
                `prompt_version`.

        Returns:
            The canonical epoch, with `lexeme_fields` sorted.
        """
        return LabelingEpoch(
            judge_model=agent_config.model_name,
            prompt_version=prompt_version(agent_config.system, agent_config.user),
            candidate_variant=config.candidate_variant,
            dense_k=config.dense_k,
            text_k=config.text_k,
            lexeme_fields=tuple(sorted(field.value for field in config.lexeme_fields)),
        )
